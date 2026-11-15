"""Sanity checks of the test harness itself."""

import subprocess
import sys


import scbi


def test_package_importable():
    assert scbi.__version__


def test_cli_help(repo_root):
    import os

    proc = subprocess.run(
        [sys.executable, "-m", "scbi", "--help"],
        cwd=repo_root,
        env={"PYTHONPATH": str(repo_root / "src"), "PATH": os.environ["PATH"],
             "SCBI_ARGV0": "scbi", "HOME": str(repo_root), "SCBI_TESTSUITE": "yes"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "scbi [options] module1" in proc.stdout
