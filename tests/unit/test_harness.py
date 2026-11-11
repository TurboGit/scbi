"""Sanity checks of the test harness itself."""

import subprocess
import sys

import pytest

import scbi


def test_package_importable():
    assert scbi.__version__


def test_cli_placeholder_fails(repo_root):
    proc = subprocess.run(
        [sys.executable, "-m", "scbi", "--version"],
        cwd=repo_root,
        env={"PYTHONPATH": str(repo_root / "src")},
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0


@pytest.mark.oracle
def test_oracle_driver_function(oracle):
    # check-tool is defined in the scbi driver, not in the runtime
    assert oracle.run("check-tool bash", check=False).returncode == 0
    assert oracle.run("check-tool no-such-tool-xyz", check=False).returncode == 1


@pytest.mark.oracle
def test_oracle_runtime_function(oracle):
    # all-variants-v is defined in the runtime (0_runtime)
    assert oracle.array("all-variants-v R a.b.c", "R") == ["a", "b", "c"]
    assert oracle.array("all-variants-v R default", "R") == []


@pytest.mark.oracle
def test_oracle_assoc_and_var(oracle):
    assert oracle.assoc("declare -A M=([x]=1 [y]='a b')", "M") == {
        "x": "1",
        "y": "a b",
    }
    assert oracle.var("V='hello world'", "V") == "hello world"
