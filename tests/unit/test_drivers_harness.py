"""The harness of the regression drivers (tests/harness.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import Driver  # noqa: E402


def driver(tmp_path) -> Driver:
    return Driver(tmp_path, __file__)


def test_clean_output_and_diff(tmp_path):
    t = driver(tmp_path)
    t.output = (f"2026/11/16 11:00:00 : build in {tmp_path}/x   \n"
                "2026/11/16 11:00:00 : x (FAILED) scbi replay /a/logs/build.cmd\n"
                "plan (0123456789abcdef0123)\n\n")
    assert t.clean_diff("""\
2024/01/01 00:00:00 : build in <pwd>/x
xxxx/xx/xx xx:xx:xx : x (FAILED) <reproduce> /a/logs/build.cmd
plan (xxxxxxxxxxxxxxxxxxxx)
""")
    assert t.failures == []


def test_failures_do_not_stop(tmp_path):
    t = driver(tmp_path)
    t.runs("echo one; false")
    t.diff("two\n")
    t.runs("echo three")
    assert t.checks == 3 and len(t.failures) == 2
    assert "RUNS echo one; false: status 1" in t.failures[0]
    assert "-two\n+one" in t.failures[1]
    assert t.output == "three\n"


def test_shell_state_kept(tmp_path):
    t = driver(tmp_path)
    t.sh("X=1\nhello() { echo hi $X; }\ndeclare -fx hello\nmkdir -p d && cd d")
    t.runs("hello; pwd")
    assert t.output == f"hi 1\n{tmp_path}/d\n"
    t.set("Y", "$X-2")
    assert t.value("$Y") == "1-2"
    t.sh("sed -i s/hi/HI/ $TEST_OUTPUT")
    assert t.output.startswith("HI 1")


def test_grep_and_values(tmp_path):
    t = driver(tmp_path)
    (tmp_path / "f.txt").write_text("in the file\n")
    t.runs("echo in the output")
    assert t.grep("in the output") and t.grep("in the file", "f.txt") and t.ngrep("nowhere")
    assert t.ok("-f f.txt") and t.nok("-d f.txt")
    assert t.is_('"$(cat f.txt)"', "==", '"in the file"') and t.isnt("a", "==", "b")
    assert t.text("v=\\$X $((1 + 1))\n") == "v=$X 2\n"
    assert t.failures == []
