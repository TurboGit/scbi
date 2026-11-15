"""The driver end-to-end on the plug-ins of the repository (scripts.d)."""

import os
import subprocess
import sys

import pytest

#  scbi show on the real plug-ins, output checked for a few known lines
REAL_SHOW_CASES = [
    (["show", "--rdepends", "c-gprbuild"], "c-gnatcoll-core"),
    (["show", "--depends", "c-gps"], "c-gprbuild"),
    (["show", "--externals:only", "--no-version", "c-libadalang"], "python3-mako"),
    (["show", "--rdepends", "c-sandbox"], "c-aws-tools (test)"),
]


@pytest.mark.parametrize("args, expected", REAL_SHOW_CASES, ids=lambda a: " ".join(a) if isinstance(a, list) else "")
def test_show_real_plugins(repo_root, tmp_path, args, expected):
    env = {"PYTHONPATH": str(repo_root / "src"), "PATH": os.environ["PATH"], "HOME": str(tmp_path),
           "SCBI_ARGV0": "scbi", "SCBI_TESTSUITE": "yes", "SCBI_ROOT": str(tmp_path / "root"),
           "SCBI_EMAIL_NOTIFICATION": "no", "LANG": "C"}
    rp = subprocess.run([sys.executable, "-m", "scbi", f"--plugins={repo_root}/scripts.d", *args],
                        cwd=tmp_path, env=env, capture_output=True, text=True)
    assert rp.returncode == 0 and rp.stderr == "", rp.stderr
    assert expected in rp.stdout
