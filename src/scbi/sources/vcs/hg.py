"""Mercurial (port of hg-co, hg-branch and the mercurial cases of
get-vcs-commit-id, get-vcs-ref and vcs-build-id)."""

from __future__ import annotations

import hashlib
import os
import subprocess

from scbi.bashcompat import words
from scbi.sources.vcs.base import Vcs, VcsRun


class Mercurial(Vcs):
    names = ("hg", "mercurial")
    label = "mercurial"
    id_kind = "revision"
    default_ref = "default"
    tool = "hg"
    marker = ".hg"

    def checkout(self, r: VcsRun, url: str, options: str, name: str, dir: str) -> int:
        url = url[:-1] if url.endswith("/") else url
        repo = dir or url.rsplit("/", 1)[-1]
        os.makedirs(f"{r.bdir}/.vcs", exist_ok=True)
        if not r.cd(f"{r.bdir}/.vcs"):
            return 1
        if not r.isdir(repo):
            res = r.run("hg", "clone", *words(url), *words(repo))
        else:
            r.cd(repo)
            if not r.isdir(".hg"):
                r.logger.ilog("build", "error:", *words(r.cwd), "not", "a", "mercurial", "repository")
                return 1
            res = r.run("hg", "pull")
        if res != 0:
            return res
        if not r.cd(f"{r.bdir}/{name}"):
            return 1
        return r.run("ln", "-s", f"../.vcs/{repo}", "vcs")

    def branch(self, r: VcsRun, options: str, module: str, branch: str, dir: str,
               *, fetched: bool = False) -> int:
        r.cd(f"{r.bdir}/{module}/vcs")
        r.run("hg", "pull")
        if branch == "NONE":
            branch = "default"
        if r.run("hg", "branch", "-f", *words(branch)) != 0:
            r.logger.ilog("build", "error: switching mercurial branch")
            return 1
        return 0

    def commit_id(self, short: bool, dir: str, env: dict[str, str]) -> str:
        proc = subprocess.run(["hg", "id", "-i", f"{dir}/"], env=env, stdin=subprocess.DEVNULL, capture_output=True)
        return proc.stdout.decode(errors="surrogateescape").rstrip("\n")

    def source_id(self, r: VcsRun) -> str:
        def out(*args: str) -> bytes:
            return subprocess.run(list(args), cwd=r.cwd, env=r.env, stdin=subprocess.DEVNULL,
                                  capture_output=True).stdout

        hver = out("hg", "identify", "--num").decode(errors="surrogateescape").rstrip("\n")
        diff = out("hg", "diff").split(b"\n")
        #  hg diff | tail -n+4
        tail = b"\n".join(diff[3:]) if len(diff) > 3 else b""
        return hver + hashlib.md5(tail).hexdigest()
