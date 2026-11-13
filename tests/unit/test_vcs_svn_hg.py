"""Subversion and Mercurial support (sources/vcs/svn.py, hg.py) compared
with svn-co / svn-branch / hg-co / hg-branch and their parts of
get-vcs-commit-id and vcs-build-id (scripts.d/4_scm)."""

import re
import shutil
import subprocess
import tarfile

import pytest

from oracle import REPO_ROOT, BashOracle
from test_vcs_git import bash_script, mask, python_run

REPOS = REPO_ROOT / "tests" / ".root" / "repos"


def svn_repos(root):
    root.mkdir(parents=True)
    for name in ("repostd", "repomlt"):
        with tarfile.open(REPOS / f"{name}.tar.bz2") as t:
            t.extractall(root, filter="tar")
    return {"std": f"file://{root}/repostd", "mlt": f"file://{root}/repomlt/"}


def svn_scenario(r):
    #  svn-branch: (op, module, BRANCH, OPTIONS, DIR)
    return [
        ("co", "std", r["std"], "none"), ("br", "std", "NONE", "none"), ("id", "std"),
        ("rmvcs", "std"), ("co", "std", r["std"], "none"), ("br", "std", "v1", "none"), ("id", "std"),
        ("rmvcs", "std"), ("co", "std", r["std"], "none"), ("br", "std", "v1.0", "none"),
        ("rmvcs", "std"), ("co", "std", r["std"], "none"), ("br", "std", "nothere", "none"),
        ("co", "mlt", r["mlt"], "none"), ("br", "mlt", "NONE", "none", "prj1"), ("id", "mlt"),
        ("rmvcs", "mlt"), ("co", "mlt", r["mlt"], "none"), ("br", "mlt", "v1", "none", "prj2"),
        ("rmvcs", "mlt"), ("co", "mlt", r["mlt"], "none"), ("br", "mlt", "v1.0", "none", "prj1"),
        ("co", "bad", "file:///nothere/repo", "none"),
    ]


def hg_scenario(root):
    root.mkdir(parents=True)
    repo = root / "simple"
    subprocess.run(["hg", "clone", "-q", str(REPOS / "simple.mercurial.bundle"), str(repo)], check=True)
    return [
        ("co", "simple", str(repo), "none"), ("br", "simple", "NONE", "none"), ("id", "simple"),
        ("br", "simple", "other", "none"), ("id", "simple"),
        ("rmvcs", "simple"), ("co", "simple", str(repo) + "/", "none"), ("id", "simple"),
        ("co", "bad", "/nothere/repo", "none"),
    ]


def compare(tmp_path, vcs, steps):
    bw = tmp_path / "bash"
    oracle = BashOracle(bw)
    bdir = bw / "bdir"
    bdir.mkdir()
    env = {"SCBI_BDIR": str(bdir), "SCBI_LOGS": str(bw / "logs"), "TODAY": "today", "SCBI_TARGET": "tgt"}
    rb = oracle.run(bash_script(steps, vcs), env, check=False)
    pw = tmp_path / "python"
    pbdir = pw / "bdir"
    pbdir.mkdir(parents=True)
    py_out = python_run(steps, pbdir, pw / "logs", vcs)
    bash_out = rb.stdout.splitlines()
    assert py_out == bash_out
    #  hg/svn write the full path of the repositories in the logs
    blog = mask((bw / "module.log").read_text(), bw)
    plog = mask((pw / "module.log").read_text(), pw)
    assert plog == blog
    for d in sorted(p.relative_to(bdir) for p in bdir.glob("*/*")):
        b, p = bdir / d, pbdir / d
        assert p.is_symlink() == b.is_symlink(), d
        if b.is_symlink():
            assert str(p.readlink()) == str(b.readlink()), d
    return bash_out


@pytest.mark.oracle
@pytest.mark.skipif(not shutil.which("svn"), reason="svn not installed")
def test_svn_same_as_bash(tmp_path):
    out = compare(tmp_path, "svn", svn_scenario(svn_repos(tmp_path / "repos")))
    assert "br 1" in out and any(re.match(r"sid r\d", line) for line in out)


@pytest.mark.oracle
@pytest.mark.skipif(not shutil.which("hg"), reason="hg not installed")
def test_hg_same_as_bash(tmp_path):
    out = compare(tmp_path, "hg", hg_scenario(tmp_path / "repos"))
    assert any(line.startswith("sid 0") for line in out)
