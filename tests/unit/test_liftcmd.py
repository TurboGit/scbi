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
     "OPTIONS =\nOPTIONS = config-options\ncmake $OPTIONS ../src\n"),
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
    ("[[ -f x ]] && rm x", "if is-file(x):\n    rm x\n"),
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
    "eval x", "while true; do", "( cd a\nmake )\nmake", "echo ${PATH//:/ }", "echo $((1 + 2))",
    "echo `date`", "read X", "echo $1", "X+=1", "if [[ $X == *a* ]]; then\n    true\nfi",
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
