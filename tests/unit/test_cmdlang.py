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
    #  an escape inside ${...} is the one of its pattern or word
    status, _, _ = run(tmp_path, 'X = /p/lib\nwrite g:\n    ${X/$PREFIX/\\$R} \\$X ${X#\\$}')
    assert (tmp_path / "g").read_text() == "$R/lib $X /p/lib\n" and status == 0


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


def test_copy(tmp_path):
    (tmp_path / "d" / "sub").mkdir(parents=True)
    (tmp_path / "d" / "sub" / "f").write_text("f")
    (tmp_path / "d" / "lnk").symlink_to("sub/f")
    (tmp_path / "a.h").write_text("a")
    (tmp_path / "b.h").write_text("b")
    (tmp_path / "out").mkdir()
    text = """
copy a.h one.h
copy *.h out
copy d out
copy d out
copy d newdir
copy d newdir
"""
    status, out, _ = run(tmp_path, text)
    assert (status, out) == (0, "")
    assert (tmp_path / "one.h").read_text() == "a"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a.h", "b.h", "d", "one.h"]
    #  recursive, links kept as links, an existing directory is merged
    assert (tmp_path / "out" / "d" / "sub" / "f").read_text() == "f"
    assert os.readlink(tmp_path / "out" / "d" / "lnk") == "sub/f"
    #  as cp -r: the first copy creates newdir, the second one copies into it
    assert (tmp_path / "newdir" / "sub" / "f").is_file() and (tmp_path / "newdir" / "d" / "sub" / "f").is_file()
    #  existing file replaced
    (tmp_path / "one.h").write_text("old")
    assert run(tmp_path, "copy b.h one.h")[0] == 0 and (tmp_path / "one.h").read_text() == "b"


@pytest.mark.parametrize("text, message", [
    ("copy -r a.h out", "copy: no option supported: -r"),
    ("copy a.h", "copy: missing destination"),
    ("copy nothere out", "copy: cannot stat 'nothere': No such file or directory"),
    ("copy a.h b.h nodir", "copy: target 'nodir' is not a directory"),
])
def test_copy_errors(tmp_path, text, message):
    (tmp_path / "a.h").write_text("a")
    (tmp_path / "b.h").write_text("b")
    (tmp_path / "out").mkdir()
    status, out, _ = run(tmp_path, text)
    assert status == 1 and out == f"m.yaml: config: line 10: {message}\n"


def test_ok_external_command(tmp_path):
    text = ('if ok("sh -c \'echo out; exit {}\'"):\n    echo yes\nelse:\n    echo no')
    assert run(tmp_path, text.format(0))[:2] == (0, "yes\n")  # stdout discarded
    assert run(tmp_path, text.format(3))[:2] == (0, "no\n")
    text = 'if ok("ls $(if cross then --nope) . 2> /dev/null"):\n    echo yes'
    assert run(tmp_path, text)[:2] == (0, "yes\n")  # empty word removed, redirection
    assert run(tmp_path, 'if ok("ls --nope 2> /dev/null"):\n    echo yes\nelse:\n    echo no')[:2] == (0, "no\n")


def test_function_in_words(tmp_path):
    def go(text):
        out = []
        state = State({}, {"PATH": os.environ["PATH"]}, str(tmp_path), out.append, out.append)
        r = make(tmp_path, config_options=lambda: ["-DA=1", "-DB=x y"])
        return r.run(parse(text, 10), state), "".join(out)
    #  a list alone in an unquoted word: one argument per element
    assert go('printf "<%s>" $(config-options) end') == (0, "<-DA=1><-DB=x y><end>")
    #  in a larger word or quoted: joined with spaces
    assert go('printf "<%s>" -D$(config-options)') == (0, "<-D-DA=1 -DB=x y>")
    assert go('printf "<%s>" "$(all-variants a.b)" $(all-variants default) z') == (0, "<a b><z>")
    assert go('printf "<%s>" $(output-words echo "u  v") $(output echo "u  v")') == (0, "<u><v><u  v>")
    assert go('printf "<%s>" $(dirname /a/b/c)$(uppercase x)') == (0, "</a/bX>")
    #  same value as an assignment
    assert go('O = config-options\nprintf "<%s>" $O') == go('printf "<%s>" $(config-options)')
    status, out = go("echo $(nope x)")
    assert status == 1 and out.startswith("m.yaml: config: line 10: unknown function $(nope ...)")


def test_delete_only_in_the_sandbox(tmp_path):
    sandbox = tmp_path / "bdir"
    (sandbox / "m" / "install" / "lib").mkdir(parents=True)
    (sandbox / "m" / "install" / "lib" / "a.la").write_text("x")
    (sandbox / "m" / "install" / "lib" / "b.la").write_text("x")
    (sandbox / "m" / "install" / "bin").mkdir()
    outside = tmp_path / "outside"
    (outside / "keep").mkdir(parents=True)
    (outside / "keep" / "f").write_text("x")
    #  a link in the sandbox to a directory outside, and a link to a file
    (sandbox / "m" / "link").symlink_to(outside / "keep")
    env = {"SCBI_BDIR": str(sandbox)}

    def go(text, cwd=sandbox / "m"):
        out = []
        state = State({}, {"PATH": os.environ["PATH"]}, str(cwd), out.append, out.append)
        return make(tmp_path, env).run(parse(text, 10), state), "".join(out)

    #  globs, files and directories (recursively), missing paths ignored
    #  delete: a directory is an error (nothing deleted)
    status, out = go("delete install/lib/a.la install/bin")
    assert status == 1 and "is a directory (use delete-tree)" in out
    assert (sandbox / "m" / "install" / "lib" / "a.la").exists()
    assert go("delete-tree install/lib/*.la install/bin nope") == (0, "")
    assert not (sandbox / "m" / "install" / "bin").exists()
    assert list((sandbox / "m" / "install" / "lib").iterdir()) == []
    #  a symbolic link is removed, not its target
    assert go("delete link") == (0, "")
    assert not (sandbox / "m" / "link").exists() and (outside / "keep" / "f").exists()
    (sandbox / "m" / "link").symlink_to(outside / "keep")
    #  outside the sandbox: refused, nothing deleted
    for path in (str(outside / "keep"), "../../outside/keep", "link/f", "link/../keep", "..",
                 str(sandbox), f"{sandbox}/m/..", "/"):
        status, out = go(f"delete-tree install {path}")
        assert status == 1 and "is not in the sandbox" in out and "nothing deleted" in out, path
        assert (outside / "keep" / "f").exists() and (sandbox / "m" / "install").exists(), path
    #  inside: a directory reached through .. but still in the sandbox
    assert go("delete-tree ../m/install") == (0, "")
    assert not (sandbox / "m" / "install").exists()
    #  no option, no operand, no sandbox
    assert go("delete -fr x")[0] == 1 and go("delete")[0] == 1
    out = []
    state = State({}, {"PATH": os.environ["PATH"]}, str(sandbox), out.append, out.append)
    assert make(tmp_path).run(parse("delete m", 10), state) == 1 and "SCBI_BDIR" in "".join(out)
    assert (sandbox / "m").exists()


def test_replace(tmp_path):
    status, out, _ = run(tmp_path, "echo $(replace 3.12.1 . _) $(replace a-b_c -_)\nX = replace 'a b' ' ' :\necho $X")
    assert (status, out) == (0, "3_12_1 abc\na:b\n")
    status, out, _ = run(tmp_path, "echo $(replace abc ab x)")
    assert status == 0 and "do not have the same length" in out


def test_value_functions_in_assignments(tmp_path):
    (tmp_path / "f1").write_text("")
    status, out, _ = run(tmp_path, "Y = ls f1\necho [$Y]\nZ = dirname /a/b\necho [$Z]")
    assert (status, out) == (0, "[f1]\n[/a]\n")


def test_get_version_of_a_plugin_in_commands(tmp_path):
    from scbi.plan import PlanState

    r = make(tmp_path)
    r.ctx.plan = PlanState({"lib2": "lib2:2.0.1"})
    out = []
    state = State({}, {"PATH": os.environ["PATH"]}, str(tmp_path), out.append, out.append)
    assert r.run(parse("V = get-version lib2\necho $V $(get-version lib2)", 10), state) == 0
    assert "".join(out) == "2.0.1 2.0.1\n"


def test_for_several_names(tmp_path):
    status, out, _ = run(tmp_path, "L = a 1 b 2 c\nfor N V in $L:\n    echo $N=$V")
    assert (status, out) == (0, "a=1\nb=2\nc=\n")


def test_log(tmp_path):
    #  with the driver: the callback (level, message)
    logged = []
    status, out, _ = run(tmp_path, "X = b\nlog 1 a $X\nlog 2 50% done\nlog 1", log=lambda n, m: logged.append((n, m)))
    assert (status, out, logged) == (0, "", [(1, "a b"), (2, "50% done"), (1, "")])
    #  without: the message indented, to the output (redirections apply)
    status, out, _ = run(tmp_path, "log 1 a b\nlog 2 c > f\ncat f")
    assert (status, out) == (0, "  a b\n    c\n")
    for bad in ("log 0 x", "log x y", "log", "log -1 x"):
        status, out, _ = run(tmp_path, bad)
        assert status == 1 and "log: level must be an integer >= 1" in out, bad
