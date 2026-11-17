"""scbi replay --script: the generated Bash script does what the
interpreter does (same output, files and status)."""

import os
import subprocess
from pathlib import Path

import pytest

from scbi.hooks.cmdlang import State, parse
from scbi.steps import replay
from scbi.steps.replayscript import ScriptError, script


def make(tmp_path, run, **kw) -> replay.Replay:
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "LANG": "C"}
    data = dict(module="m", variant="default", hook="build", function="m-build", plugin_file="m.yaml",
                cwd=str(tmp_path), host="x86_64-linux-gnu", target="x86_64-linux-gnu", run=run,
                params={"PREFIX": str(tmp_path / "inst"), "TARGET": "x86_64-linux-gnu", "VARIANT": "default"},
                variables={"V": "plugin-var"}, driver={"SCBI_JOBS": "4", "SCBI_CMAKE_BUILD_TYPE": "Debug", "SCBI_BDIR": str(tmp_path)},
                environment=env, config_options=["-DA=1", "-DB=x y"], version="1.2")
    data.update(kw)
    return replay.Replay(**data)


def interpreted(r: replay.Replay) -> tuple[int, str]:
    out: list[str] = []
    state = State(dict(r.variables), dict(r.environment), r.cwd, out.append, lambda t: None)
    status = replay.runner(r, replay.context(r)).run(parse(r.run, r.line), state)
    return status, "".join(out)


def scripted(r: replay.Replay, inline: bool = False) -> tuple[int, str]:
    #  standard output and status (the error messages differ)
    proc = subprocess.run(["/bin/bash", "-c", script(r, inline=inline)], capture_output=True, text=True, cwd="/",
                          env={})
    return proc.returncode, proc.stdout


BODIES = [
    "echo $PREFIX $TARGET $VARIANT $V $SCBI_JOBS",
    "printf '<%s>' $(config-options) end\necho",
    'O = config-options\nprintf "<%s>" $O\necho',
    'printf "<%s>" "$(config-options)"\necho',
    "BT = get-build-type CMAKE Release\necho $BT $(get-version)",
    "X = a b\nprintf '<%s>' $X\necho\nY = \"a b\"\nprintf '<%s>' $Y\necho",
    "if cross:\n    echo cross\nelif variant == default:\n    echo native default\nelse:\n    echo other",
    "mkdir -p d/e\nif is-dir(d/e) and not is-file(d/e):\n    echo dir\nif exists(nope):\n    echo no",
    "E =\nif empty($E):\n    echo empty\nF = x\nif not empty($F):\n    echo full",
    'if ok("test -d /"):\n    echo ok\nif not ok("ls /nope 2> /dev/null"):\n    echo ko',
    "false\nif status != 0:\n    echo failed",
    "false || echo or\ntrue && echo and",
    "for X in a b c:\n    echo item $X",
    "S = output echo hello world\necho [$S]\nW = output-words echo a b\nprintf '<%s>' $W\necho",
    "write f.txt:\n    value $V\n    \\$HOME kept\nappend f.txt:\n    more\nwrite-raw g.txt:\n    $V raw\ncat f.txt g.txt",
    "mkdir -p src/sub\necho x > src/sub/a\ncopy src dst\ncat dst/sub/a",
    "check-versions 1.10 '>' 1.9 && echo newer",
    "if version(m) >= 1.0:\n    echo v\nif ref == 1.2:\n    echo ref",
    "echo $(uppercase $VARIANT) $(basename /a/b/c)",
    "X = output echo plugin-var/x/y\necho ${X#$V/} ${X/$V/@}",
    "L = a 1 b 2 c\nfor N W in $L:\n    echo $N=$W",
    "X = output echo plugin-var/x\nwrite f:\n    ${X/$V/\\$R} \\$V ${X#\\$}\ncat f",
    "Z = dirname /a/b\necho $Z\nU = uppercase $VARIANT x\necho $U",
    "cd inst-not-there || echo nocd\nmkdir -p w\ncd w\npwd",
    "X = $(if cross then a else b)\necho $X",
    "echo one\nreturn 3\necho never",
    r"""echo 'single $V' "double $V" a\;b""",
    "mkdir -p d/e\ntouch d/f\ndelete d/e || echo dir\ndelete-tree d/e d/nope\nls d\ndelete d/f\nls d\n"
    "delete-tree /tmp || echo refused\nls -d d",
    "echo $(replace 3.12 . _) $(replace a-b -)\nX = output echo 1.2\necho $(replace $X . _) $(replace $X .)",
]


@pytest.mark.parametrize("body", BODIES)
@pytest.mark.parametrize("inline", [False, True], ids=["script", "inline"])
def test_script_same_as_interpreter(tmp_path, body, inline):
    (tmp_path / "inst").mkdir()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ra, rb = make(a, body), make(b, body)
    rb.params["PREFIX"] = str(b / "inst")
    sa, outa = interpreted(ra)
    sb, outb = scripted(rb, inline)
    assert (sb, outb.replace(str(b), "@")) == (sa, outa.replace(str(a), "@"))


def test_functions_and_header(tmp_path):
    r = make(tmp_path, "greet world", functions={"greet": {"params": ["WHO"], "run": "echo hello $WHO\nreturn 0\n"}})
    text = script(r)
    assert text.startswith("#!/bin/bash\n")
    #  only the environment: the other variables are replaced by their value
    assert "export PATH=" in text and "SCBI_" not in text and "CONFIG_OPTIONS" not in text
    #  the variables of the user's terminal are not written
    assert "HOME=" not in text and "LANG=" not in text
    assert "greet()\n{\n    local WHO=$1\n" in text
    assert scripted(r) == scripted(r, inline=True) == interpreted(r) == (0, "hello world\n")


def test_values_written(tmp_path):
    r = make(tmp_path, "cmake -DP=$PREFIX $(config-options) -j$SCBI_JOBS ../src\nX = output date\necho $X")
    lines = script(r).splitlines()
    assert f"cmake -DP={tmp_path}/inst -DA=1 '-DB=x y' -j4 ../src" in lines
    assert 'echo "$X"' in lines
    inline = script(r, inline=True)
    assert inline.startswith(f"( cd {tmp_path} || exit 1; export ") and inline.endswith(" )\n")
    assert inline.count("\n") == 1


def test_not_available(tmp_path):
    with pytest.raises(ScriptError, match="all-modules"):
        script(make(tmp_path, "for M in $(all-modules):\n    echo $M"))
