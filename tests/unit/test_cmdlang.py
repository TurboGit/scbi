"""The command language of command hooks (scbi.hooks.cmdlang)."""

import os
from pathlib import Path

import pytest

from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.cmdlang import CmdSyntaxError, Runner, State, parse, tokenize
from scbi.hooks.context import HookContext


def make(tmp_path, env=None, **kw):
    sv = ShellVars({"SCBI_CMAKE_BUILD_TYPE": "Debug", **(env or {})}, set())
    ctx = HookContext(module="m", variant="default", hook="config",
                      params={"PREFIX": "/p", "TARGET": "x86_64", "VARIANT": "default"},
                      env=Environment(sv), host="x86_64", target="x86_64", cwd=tmp_path)
    return Runner(ctx, "m.yaml: config", **kw)


def run(tmp_path, text, env=None, **kw):
    out = []
    state = State({}, {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}, str(tmp_path), out.append, out.append)
    status = make(tmp_path, env, **kw).run(parse(text, 10), state)
    return status, "".join(out), state


def test_tokenize():
    words = tokenize("""a 'b c' "d $X" e\\ f >out 2>&1 g&&h""")
    texts = ["".join(t for t, _ in w.parts) if not isinstance(w, str) else w for w in words]
    assert texts == ["a", "b c", "d $X", "e f", ">", "out", "2>&1", "g", "&&", "h"]


def test_commands_and_status(tmp_path):
    status, out, _ = run(tmp_path, "echo hello $PREFIX\nprintf '%s-%s\\n' a b\nfalse")
    assert out == "hello /p\na-b\n"
    assert status == 1  # status of the last step
    status, out, _ = run(tmp_path, "false && echo no\nfalse || echo yes\ntrue")
    assert (status, out) == (0, "yes\n")


def test_variables_and_lists(tmp_path):
    text = """
X = a b c
Y = "one two"
E =
printf '[%s]' $X $Y "$X" $E
echo
Z = ${Y%% *}
echo ${Z:-none} ${UNSET:-def}
"""
    status, out, _ = run(tmp_path, text)
    assert out == "[a][b][c][one two][a b c]\none def\n"


def test_functions(tmp_path):
    (tmp_path / "d1").mkdir()
    text = """
BT = get-build-type CMAKE Release
OT = get-build-type OTHER Release
OPTS = config-options
L = last-modified-directory d*
V = output printf 'x1\\nx2\\n'
F = first-line $V
B = basename /a/b/c.txt
P = command-path printf
echo $BT $OT $L $F $B
printf '<%s>' $OPTS
"""
    status, out, state = run(tmp_path, text, config_options=lambda: ["-DA=1", "-DB=2 3"])
    assert out == "Debug Release d1 x1 c.txt\n<-DA=1><-DB=2 3>"
    assert state.vars["P"].endswith("/printf")
    assert state.vars["V"] == "x1\nx2"


def test_inline_builtin_and_env_words(tmp_path):
    status, out, _ = run(tmp_path, "echo -DCMAKE_BUILD_TYPE=$(get-build-type CMAKE Release)\n"
                                   "A=1 B=two env | grep -E '^(A|B)='\nexport C = 3\nprintenv C")
    assert out == "-DCMAKE_BUILD_TYPE=Debug\nA=1\nB=two\n3\n"


def test_if_for_cd_write(tmp_path):
    text = """
if not is-dir(build):
    mkdir build
cd build
for f in a b:
    write $f.txt:
        name $f
        prefix $PREFIX
append a.txt:
    more
write-raw raw.txt:
    $NOT_EXPANDED
if cross:
    echo cross
elif exists(a.txt):
    echo native
else:
    echo never
ls
"""
    status, out, state = run(tmp_path, text)
    assert out == "native\na.txt\nb.txt\nraw.txt\n"
    assert (tmp_path / "build" / "a.txt").read_text() == "name a\nprefix /p\nmore\n"
    assert (tmp_path / "build" / "raw.txt").read_text() == "$NOT_EXPANDED\n"
    assert state.cwd == str(tmp_path / "build")


def test_conditions(tmp_path):
    text = """
V = 1.2
if $V > 1.10:
    echo version
if ok("test -d /"):
    echo ok
if not ok("false"):
    echo notok
false
if status == 1:
    echo status
if empty($NOPE) and $TARGET == x86_64:
    echo empty
"""
    status, out, _ = run(tmp_path, text)
    assert out == "ok\nnotok\nstatus\nempty\n"


def test_redirections_and_pipes(tmp_path):
    text = """
echo one > f
echo two >> f
cat < f | wc -l > n
ls nothere 2> err
ls nothere 2>&1 > /dev/null | wc -l > n2
"""
    status, out, _ = run(tmp_path, text)
    assert (tmp_path / "f").read_text() == "one\ntwo\n"
    assert (tmp_path / "n").read_text().strip() == "2"
    assert "nothere" in (tmp_path / "err").read_text()
    assert (tmp_path / "n2").read_text().strip() == "1"


def test_globs(tmp_path):
    for f in ("a.c", "b.c", "c.h"):
        (tmp_path / f).write_text("")
    status, out, _ = run(tmp_path, "echo *.c '*.c' x*.none")
    assert out == "a.c b.c *.c x*.none\n"


def test_return_and_plugin_functions(tmp_path):
    funcs = {"greet": (("WHO",), parse("echo hi $WHO\nreturn 3"))}
    status, out, _ = run(tmp_path, "greet bob\nS = status\necho $S\nreturn 5\necho never", functions=funcs)
    assert (status, out) == (5, "hi bob\n3\n")


def test_errors(tmp_path):
    status, out, _ = run(tmp_path, "nothere-cmd a\n./nothere")
    assert status == 127
    assert out == ("m.yaml: config: line 10: nothere-cmd: command not found\n"
                   "m.yaml: config: line 11: ./nothere: No such file or directory\n")
    status, out, _ = run(tmp_path, "cd nodir")
    assert status == 1 and "cd: nodir: No such file or directory" in out


@pytest.mark.parametrize("text, line", [
    ("if cross\n  echo", 1),
    ("if cross:\necho", 1),
    ("  echo", 1),
    ("else:\n  echo", 1),
    ("echo 'x", 1),
    ("if version(:\n  echo", 1),
    ("X = a | b", 1),
    ("echo a |", 1),
    ("echo >", 1),
    ("while true:\n  echo", 1),
])
def test_syntax_errors(text, line):
    with pytest.raises(CmdSyntaxError) as e:
        parse(text)
    assert e.value.line == line


def test_streaming_large_output(tmp_path):
    status, out, _ = run(tmp_path, "seq 1 20000")
    assert out.splitlines()[-1] == "20000" and status == 0


def test_escapes_pwd_and_status(tmp_path):
    text = """
echo "a \\$PREFIX $PREFIX" \\$X
write f:
    run \\$1 in $PREFIX \\\\ \\`x\\`
echo $PWD
return -1
"""
    status, out, _ = run(tmp_path, text)
    assert out == f"a $PREFIX /p $X\n{tmp_path}\n"
    assert (tmp_path / "f").read_text() == "run $1 in /p \\ `x`\n"
    assert status == 255  # modulo 256, as Bash


def test_variant_builtins(tmp_path):
    text = """
V = all-variants a.b
D = all-variants default
printf '<%s>' $V $D
check-versions 1.10 ">" 1.9 && echo gt
check-versions 1.2 ">" 1.9 || echo le
"""
    status, out, _ = run(tmp_path, text)
    assert out == "<a><b>gt\nle\n"


def test_trace_and_script_without_shebang(tmp_path):
    script = tmp_path / "configure"
    script.write_text("echo configured $1\n")
    script.chmod(0o755)
    lines = []
    out = []
    state = State({}, {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}, str(tmp_path), out.append, out.append)
    runner = make(tmp_path, trace=lines.append)
    status = runner.run(parse("X = a 'b c'\nA=1 ./configure --prefix=$PREFIX"), state)
    assert status == 0 and "".join(out) == "configured --prefix=/p\n"
    assert lines == ["_TRACE: X=a 'b c'", "_TRACE: A=1 ./configure --prefix=/p"]


def test_string_functions_and_if(tmp_path):
    text = """
BT = get-build-type CMAKE Release
A = if $BT == Debug then ON else OFF
B = if build-type(CMAKE,Release) != Debug then ON else OFF
U = uppercase $VARIANT
L = lowercase ABC
echo $A $B $U $L
echo -DX=$(if $BT == Debug then yes) $(uppercase $L)
"""
    status, out, _ = run(tmp_path, text)
    assert (status, out) == (0, "ON OFF DEFAULT abc\n-DX=yes ABC\n")


def test_if_assign_syntax_error():
    with pytest.raises(CmdSyntaxError):
        parse("A = if $BT == Debug ON else OFF", 1)
