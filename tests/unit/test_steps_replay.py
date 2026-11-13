"""Replay files of interpreted command hooks (steps/replay.py)."""

import os

from scbi.steps import replay


def test_replay_round_trip(tmp_path, capsys):
    r = replay.Replay(
        module="m", variant="default", hook="build", function="m-build", plugin_file="/p/m.yaml",
        cwd=str(tmp_path), host="x86_64", target="x86_64",
        run="echo build $PREFIX $LIBS $(get-build-type MAKE rel)\nhelper one\nOPTS = config-options\necho $OPTS\n",
        line=12, params={"PREFIX": "/inst", "TARGET": "x86_64", "VARIANT": "default"},
        variables={"LIBS": "static"}, driver={"SCBI_MAKE_BUILD_TYPE": "debug"},
        environment={"PATH": os.environ["PATH"], "HOME": str(tmp_path)},
        config_options=["-DA=1", "-DB=2 3"],
        functions={"helper": {"params": ["X"], "run": "echo helper $X", "line": 30}})
    path = str(tmp_path / "build.cmd")
    replay.write(path, r)
    assert open(path).readline() == f"# scbi replay {path}\n"
    assert replay.load(path) == r
    assert replay.replay(path) == 0
    assert capsys.readouterr().out == "build /inst static debug\nhelper one\n-DA=1 -DB=2 3\n"
    assert replay.replay(path, trace=True) == 0
    assert "_TRACE: helper one\n" in capsys.readouterr().out


def test_replay_error_location(tmp_path, capsys):
    r = replay.Replay(module="m", variant="default", hook="build", function="m-build",
                      plugin_file="/p/m.yaml", cwd=str(tmp_path), host="h", target="h",
                      run="true\nnothere-cmd\n", line=7, environment={"PATH": os.environ["PATH"]})
    path = str(tmp_path / "build.cmd")
    replay.write(path, r)
    assert replay.replay(path) == 127
    assert capsys.readouterr().out == "m.yaml: build: line 8: nothere-cmd: command not found\n"
