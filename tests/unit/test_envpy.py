"""Python environment files (scbi.envpy) and the converter of the Bash
ones (scbi.envconvert)."""

from pathlib import Path

import pytest

from scbi import envconvert, envpy


def dirs(tmp_path):
    cwd, home, plugins = tmp_path / "w", tmp_path / "h", tmp_path / "p"
    for d in (cwd, home, plugins):
        d.mkdir()
    return cwd, home, plugins


def test_search_order_and_missing(tmp_path):
    cwd, home, plugins = dirs(tmp_path)
    getvar = {}.get
    assert envpy.load("", cwd, home, plugins, getvar).path is None  # no default env: fine
    with pytest.raises(envpy.EnvFileError, match=r"\.env-x not found"):
        envpy.load("x", cwd, home, plugins, getvar)
    (plugins / ".env-x").write_text("A=1\n")
    with pytest.raises(envpy.EnvFileError, match="is a Bash file, convert it with: python3 -m scbi.envconvert"):
        envpy.load("x", cwd, home, plugins, getvar)
    (plugins / ".env-x.py").write_text("A = 'plugins'\n")
    assert envpy.load("x", cwd, home, plugins, getvar).settings == {"A": "plugins"}
    (home / ".scbi-env-x.py").write_text("A = 'home'\n")
    assert envpy.load("x", cwd, home, plugins, getvar).settings == {"A": "home"}
    (cwd / ".scbi-env-x.py").write_text("A = 'cwd'\n")
    assert envpy.load("x", cwd, home, plugins, getvar).settings == {"A": "cwd"}


def test_settings_hooks_and_errors(tmp_path):
    path = tmp_path / ".env.py"
    path.write_text("""
import os
SCBI_PLAN = getvar("SCBI_PLAN", "default")
SCBI_JOBS = getvar("SCBI_JOBS", "4")
ROOT = SCBI_ENV_DIR + "/root"
PASSTHROUGH = ["CC"]
_private = "x"
lower = "y"
COUNT = 3

def rewrite_vcs(record):
    return [f.replace("/old", "/new") for f in record]

def helper():
    pass
""")
    env = envpy.run(path, {"SCBI_JOBS": "8"}.get)
    assert env.settings == {"SCBI_PLAN": "default", "SCBI_JOBS": "8", "ROOT": f"{tmp_path}/root"}
    assert env.passthrough == ("CC",)
    assert set(env.hooks) == {"rewrite_vcs"}
    assert env.hook("rewrite_vcs")(["none", "none", "git", "/old/x"]) == ["none", "none", "git", "/new/x"]
    path.write_text("PASSTHROUGH = 'CC'\n")
    with pytest.raises(envpy.EnvFileError, match="PASSTHROUGH must be a list"):
        envpy.run(path, {}.get)
    path.write_text("A = undefined_name\n")
    with pytest.raises(envpy.EnvFileError, match="NameError"):
        envpy.run(path, {}.get)


def test_convert(tmp_path):
    text, issues = envconvert.convert_text(
        "# comment\nSCBI_PLAN=${SCBI_PLAN:-default}\nexport A=\"x $B/y\"\nV='a b'\n")
    assert issues == []
    assert text.split("\n")[2:] == ["# comment", "SCBI_PLAN = getvar('SCBI_PLAN', 'default')",
                                    "A = 'x ' + getvar('B') + '/y'", "V = 'a b'", ""]
    #  the result runs
    path = tmp_path / "e.py"
    path.write_text(text)
    assert envpy.run(path, {"B": "/b"}.get).settings == {"SCBI_PLAN": "default", "A": "x /b/y", "V": "a b"}
    _, issues = envconvert.convert_text("function module-final-step()\n{\n    echo $1\n}\nC=${D:-${E}}\nls\n")
    assert [i.split(":")[0] for i in issues] == ["line 1", "line 5", "line 6"]


def test_repository_env_converts():
    root = Path(__file__).resolve().parents[2]
    text, issues = envconvert.convert_text((root / "scripts.d" / ".env").read_text())
    assert issues == []
    assert (root / "scripts.d" / ".env.py").read_text().split("\n")[1:] == text.split("\n")[1:]
