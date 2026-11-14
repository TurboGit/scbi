"""handle-sources (sources/handle.py) compared with the Bash function, on
a sequence of modules and references sharing the sandboxes: git, hg and
svn checkouts and updates, branches, archives, dev checkouts, native
variants, no sources and errors."""

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from oracle import REPO_ROOT
from probe import probe_pair

REPOS = REPO_ROOT / "tests" / ".root" / "repos"
ARCHIVES = REPO_ROOT / "tests" / ".root" / ".archives"

#  (FORMODULE, MODREF, extra environment, action before)
STEPS = [
    ("@root", "lib1", {}, None),
    ("@root", "lib1", {}, None),                       # up-to-date checkout
    ("@root", "lib1", {"DO_UPDATE": "yes"}, None),     # update forced
    ("@root", "lib1:v1", {}, None),                    # another branch
    ("@root", "lib1:v2.0", {}, None),                  # a tag
    ("@root", "lib1:nothere", {}, None),               # unknown reference
    ("@root", "lib1:#v1.2", {}, None),                 # archive
    ("@root", "lib1:#v1.2", {}, None),                 # archive already extracted
    ("@root", "lib1:#v9", {}, None),                   # missing archive
    ("@root", "lib1:dev", {}, None),                   # user checkout
    ("@root", "lib2:dev", {}, None),                   # no user checkout
    ("@root", "lib1/native", {}, None),
    ("@root", "lib2", {}, None),
    ("lib2", "lib1", {}, None),
    ("@root", "test4", {}, None),                      # mercurial
    ("@root", "test4", {}, None),
    ("@root", "svnstd", {}, None),                     # subversion
    ("@root", "svnstd:v1", {}, None),
    ("@root", "svnmlt", {}, None),
    ("@root", "noarchive:#1", {}, None),
    #  (the plug-in wrong, 3 values in the vcs and archive hooks, does not
    #  convert to YAML: python-deferred.txt)
    ("@root", "dep1", {}, None),                       # no vcs, no archive
    ("@root", "dep1", {}, "srcdir"),                   # no vcs, sources present
    ("@root", "lib1", {"ARCHIVE_CACHE": "yes"}, None),
    ("@root", "lib1:v1", {"DO_TEST": "yes-only"}, None),
]


def setup_repos(root: Path) -> Path:
    repos = root / "repos"
    repos.mkdir(parents=True)
    for f in REPOS.iterdir():
        if f.is_file():
            shutil.copy(f, repos / f.name)
    for name in ("repostd", "repomlt"):
        with tarfile.open(REPOS / f"{name}.tar.bz2") as t:
            t.extractall(repos, filter="tar")
    return repos


def tree(root: Path, time_ids: bool = False) -> list[str]:
    """Files (md5), links (target); ``time_ids``: the build ids depend on
    the time (not compared)."""
    result = []
    if not root.exists():
        return result
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".hg", ".svn", ".vcs")]
        for name in sorted(dirnames + filenames):
            p = Path(dirpath, name)
            rel = p.relative_to(root)
            if p.is_symlink():
                result.append(f"{rel} -> {os.readlink(p)}")
            elif p.is_file() and time_ids and name.startswith("build-id"):
                result.append(f"{rel}")
            elif p.is_file():
                result.append(f"{rel} {hashlib.md5(p.read_bytes()).hexdigest()}")
    return sorted(result)


def mask(text: str, root: Path) -> str:
    text = re.sub(r"\d{4}/\d\d/\d\d \d\d:\d\d:\d\d", "<ts>", text)
    return text.replace(str(root), "<root>")


@pytest.mark.oracle
def test_handle_sources_same_as_bash(tmp_path):
    repos = setup_repos(tmp_path)
    bash, python = probe_pair(tmp_path / "sb")
    for sb in (bash, python):
        root = sb.root / ".root"
        (root / ".archives").mkdir(parents=True, exist_ok=True)
        for f in ARCHIVES.glob("lib1-*"):
            shutil.copy(f, root / ".archives" / f.name)
        #  a user checkout of lib1 (lib1:dev)
        subprocess.run(["git", "clone", "-q", str(repos / "lib1.bundle"), str(root / "git" / "lib1.bundle")], check=True)
    env0 = {"TESTREPOS": str(repos), "GIT_ALLOW_PROTOCOL": "file", "DO_UPDATE": "no"}
    for i, (formodule, modref, extra, action) in enumerate(STEPS):
        if action == "srcdir":
            for sb in (bash, python):
                (sb.root / ".root" / "builds" / "dep1" / "src").mkdir(parents=True, exist_ok=True)
        env = {**env0, **extra}
        args = ["probe", "handle-sources", formodule, modref]
        rb, rp = bash.run(args, env), python.run(args, env)
        ctx = f"step {i}: {formodule} {modref} {extra}"
        assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), ctx
        bb, pb = bash.root / ".root" / "builds", python.root / ".root" / "builds"
        module = re.split(r"[/:]", modref)[0]
        blog, plog = bb / f"{module}.log", pb / f"{module}.log"
        assert mask(plog.read_text() if plog.exists() else "", python.root) == \
            mask(blog.read_text() if blog.exists() else "", bash.root), ctx
        time_ids = action == "srcdir"
        tp = [mask(x, python.root) for x in tree(pb / module, time_ids)]
        tb = [mask(x, bash.root) for x in tree(bb / module, time_ids)]
        assert tp == tb, ctx
