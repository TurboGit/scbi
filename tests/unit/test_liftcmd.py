"""Conversion of Bash command hooks to the command language
(scbi.plugin.liftcmd): one case per construct."""

import pytest

from scbi.plugin.liftcmd import CmdUnliftable, lift_commands


def lift(text, params=None):
    if params is None:
        params = {1: "PREFIX", 2: "TARGET", 3: "VARIANT"}
    return lift_commands(text.strip("\n").split("\n"), params)


@pytest.mark.parametrize("bash, expected", [
    ("make -j$SCBI_JOBS", "make -j$SCBI_JOBS\n"),
    ("cd build && make install", "cd build && make install\n"),
    ("local BT=$(get-build-type CMAKE Release)", "BT = get-build-type CMAKE Release\n"),
    ('local DEBUG="$(get-build-type MAKE false)"', "DEBUG = get-build-type MAKE false\n"),
    ("local OPTIONS=()\nget-config-options OPTIONS $PREFIX $TARGET $VARIANT\ncmake \"${OPTIONS[@]}\" ../src",
     "OPTIONS = config-options\ncmake $OPTIONS ../src\n"),
    ("local L=$(last-modified-directory $PREFIX/lib/python*)", "L = last-modified-directory $PREFIX/lib/python*\n"),
    ("cmake -DCMAKE_BUILD_TYPE=$(get-build-type CMAKE Release) ../src",
     "cmake -DCMAKE_BUILD_TYPE=$(get-build-type CMAKE Release) ../src\n"),
    ("cc $(pkg-config --cflags x) a.c", "_S1 = output-words pkg-config --cflags x\ncc $_S1 a.c\n"),
    ('local V=$($TOOL --version | head -1)', "V = output $TOOL --version | head -1\n"),
    ('CFLAGS="-O2 -g"', 'CFLAGS = "-O2 -g"\n'),
    ("export AWS_BUILD=relocatable", "export AWS_BUILD = relocatable\n"),
    ("PROCESSORS=$SCBI_JOBS make", "PROCESSORS=$SCBI_JOBS make\n"),
    ("if [[ $SCBI_HOST != $TARGET ]]; then\n    make cross\nelse\n    make\nfi",
     "if cross:\n    make cross\nelse:\n    make\n"),
    ("if [[ ! -h ../src/.git ]]; then\n    ln -s a b\nfi", "if not (is-link(../src/.git)):\n    ln -s a b\n"),
    ("if [[ -d $PREFIX/x && -z $Y ]]; then\n    true\nfi", "if is-dir($PREFIX/x) and (empty($Y)):\n    true\n"),
    ('if [[ "$(command -v $TOOL)" = "" ]]; then\n    echo no\nfi',
     '_S1 = command-path $TOOL\nif $_S1 == "":\n    echo no\n'),
    ("gprbuild-project prj.gpr\nif [[ $? = 0 ]]; then\n    echo ok\nfi",
     "gprbuild -p -q $(if cross then --target=$TARGET) prj.gpr -cargs -gnatwA > /dev/null 2>&1\n"
     "if status == 0:\n    echo ok\n"),
    ("if grep -q x f; then\n    echo found\nfi", 'if ok("grep -q x f"):\n    echo found\n'),
    ("[[ -f x ]] && rm x", "if is-file(x):\n    delete x\n"),
    ("for M in a b;\ndo\n    echo $M >> list\ndone", "for M in a b:\n    echo $M >> list\n"),
    ("cat <<EOF > prj.gpr\n   project p is\n   end p;\nEOF", "write prj.gpr:\n    project p is\n    end p;\n"),
    ("cat <<'EOF' >> f\n$X\nEOF", "append-raw f:\n    $X\n"),
    ("case $TARGET in\n    *mingw*)\n        make\n    ;;\n    *)\n        false\n    ;;\nesac",
     'if $TARGET =~ "^(?:.*mingw.*)$":\n    make\nelse:\n    false\n'),
    ("( cd sub\n./run.sh )", "cd sub\n./run.sh\n"),
    ('echo ${SCBI_MODULES_DIR["lib1"]}', "echo ${SCBI_MODULES_DIR[lib1]}\n"),
    ("return $?", "_STATUS = status\nreturn\n"),
])
def test_lift(bash, expected):
    assert lift(bash) == expected


def test_function_parameters():
    assert lift('echo "$1" $2', {1: "A", 2: "B"}) == 'echo "$A" $B\n'


@pytest.mark.parametrize("bash", [
    "eval x", "while true; do", "( cd a\nmake )\nmake", "echo $((1 + 2))",
    "echo `date`", "read X", "echo $1", "if [[ $X == *a* ]]; then\n    true\nfi",
    "cmd <<EOF\nx\nEOF",
])
def test_not_liftable(bash):
    with pytest.raises(CmdUnliftable):
        lift(bash, {})


def test_escaped_parameters_and_variants():
    assert lift('echo "\\$1 $1"') == 'echo "\\$1 $PREFIX"\n'
    assert lift("for V in $(all-variants $VARIANT); do\n    echo $V\ndone") == \
        "_S1 = all-variants $VARIANT\nfor V in $_S1:\n    echo $V\n"


@pytest.mark.parametrize("bash", ["call-variant-hooks opts $PREFIX", 'X="$(call-variant-hooks o)"',
                                  "true && plugin-call-variant-hooks m h"])
def test_runtime_function_not_builtin(bash):
    with pytest.raises(CmdUnliftable):
        lift(bash)


@pytest.mark.parametrize("bash, lifted", [
    ("cp main $PREFIX/bin", "copy main $PREFIX/bin"),
    ("cp -r bin $PREFIX && cp -R lib $PREFIX", "copy bin $PREFIX && copy lib $PREFIX"),
    ("cp -a x y", "cp -a x y"),
    ("cp a b | tee log", "cp a b | tee log"),
    ("cp a b > log", "cp a b > log"),
])
def test_cp_lifted_to_copy(bash, lifted):
    from scbi.plugin.liftcmd import _cp_to_copy

    assert _cp_to_copy(bash) == lifted


def test_loop_in_pipeline_unliftable():
    with pytest.raises(CmdUnliftable, match="while"):
        lift_commands(["cat MANIFEST | while read file; do", "    cp $file .", "done"])


@pytest.mark.parametrize("name, key", [
    ("m-build-runtime", ("build-runtime", "", False)),
    ("m-cross-build-runtime", ("build-runtime", "", True)),
    ("m-vcs-build-runtime", ("build-runtime", "vcs", False)),
    ("m-vcs-cross-build-runtime", ("build-runtime", "vcs", True)),
    ("m-build-env", ("build-env", "", False)),
])
def test_build_target_hook_names(name, key):
    from scbi.plugin.lift import parse_hook_name
    k = parse_hook_name("m", name)
    assert (k.hook, k.qualifier, k.cross) == key


def test_salome_idioms():
    lifted = lift_commands([
        'CXXFLAGS+=" -w" cmake "${OPTIONS[@]}" ../src',
        'F=""', 'F+=" --a=x"', './configure $F',
        'cmake ${CDEBUG:+"-DX=ON"} ..',
        'P=$(scbi-store-get-key PYPIURL)',
        'echo $(get-os-lib libGL.so)',
        'X="a b" make',
    ])
    assert lifted.splitlines() == [
        'CXXFLAGS="$CXXFLAGS -w" cmake $OPTIONS ../src',
        'F = ""', "F = $F  --a=x", "./configure $F",
        "cmake ${CDEBUG:+-DX=ON} ..",
        "P = $(store-key PYPIURL)",
        "echo $(get-os-lib libGL.so)",
        'X="a b" make',
    ]


def test_and_group_lifted():
    assert lift_commands(["[[ -d $P/x ]] &&", "    {", "        mkdir -p a", "    } || true"]) == \
        "if is-dir($P/x):\n    mkdir -p a\n"
    assert lift_commands(['[[ -d "$PREFIX"/lib ]] && {', "rmdir b", "}"]) == "if is-dir($PREFIX/lib):\n    rmdir b\n"


def test_value_lifting_salome_idioms():
    from scbi.plugin.lift import lift_env, lift_values
    from scbi.plugin.model import EnvOp, Guarded, LocalAssign

    items = lift_values([
        "local DISDOC=$(is-enabled no-doc)",
        "[[ -z ${DISDOC} ]] && echo os@-sphinx",
        "[[ ! $REF =~ 6.28 ]] && {", "echo a.patch", "echo b.patch", "}",
        "[[ -n $SCOTCH_DIR ]] && echo -DS=$SCOTCH_DIR",
        "echo -DPY=$(command -v python3) ${CDEBUG:+\"-DX=ON\"}",
        "echo -DSWIG_DIR=$(swig -swiglib)",
        "local F=-Wa",
        "local F+=\" -Wb\"",
        "echo $F",
        "false && echo never",
        "echo -DVTK=$(last-modified-directory", "\"$P/lib/cmake/paraview-*\")",
    ]).items
    assert items == (
        Guarded("not enabled(no-doc)", ("os@-sphinx",)),
        Guarded("not (ref =~ 6.28)", ("a.patch", "b.patch")),
        Guarded("not empty($SCOTCH_DIR)", ("-DS=$SCOTCH_DIR",)),
        "-DPY=$(command-path python3) ${CDEBUG:+-DX=ON}",
        "-DSWIG_DIR=$(output swig -swiglib)",
        "-Wa -Wb",
        '-DVTK=$(last-modified-directory "$P/lib/cmake/paraview-*")',
    )
    ops = lift_env(["unset PYTHONHOME", "local W=$(cygpath -w $PREFIX)", "set-var X $W"]).ops
    assert ops == (EnvOp("unset-var", ("PYTHONHOME",)), LocalAssign("W", "$(output cygpath -w $PREFIX)"),
                   EnvOp("set-var", ("X", "$W")))


def test_compiler_env_helpers_not_lifted():
    #  the compiler environment comes from a c-sandbox variant
    from scbi.plugin.lift import _Unliftable, lift_env

    for line, hint in (("system-compiler", "c-sandbox/system"), ("target-env", "c-sandbox in"),
                       ("no-target-env /p", "c-sandbox/host")):
        with pytest.raises(_Unliftable, match=hint):
            lift_env([line, "add-to-var PATH /x"])


def test_rm_lifted_to_delete():
    assert lift_commands(["rm -fr build/kb", "rm -rf a b && make", "rm -f x", "rm y *.o", "rm -fr -v y",
                          "rm -r z | cat", "rm -i w"]) == (
        "delete-tree build/kb\ndelete-tree a b && make\ndelete x\ndelete y *.o\nrm -fr -v y\nrm -r z | cat\n"
        "rm -i w\n")


def test_empty_list_replaced():
    #  local X=() then X set: no empty assignment (never read); kept when
    #  the next line reads it
    assert lift_commands(["local OPTIONS=()", "get-config-options OPTIONS $PREFIX $TARGET $VARIANT",
                          '../src/configure "${OPTIONS[@]}"']) == \
        "OPTIONS = config-options\n../src/configure $OPTIONS\n"
    assert lift_commands(["local L=()", 'L=("${L[@]}" a)', 'echo "${L[@]}"']) == "L =\nL = $L a\necho $L\n"
    #  a value before an assignment is not the empty list
    assert lift_commands(["X=a", "X=b", "echo $X"]) == "X = a\nX = b\necho $X\n"
