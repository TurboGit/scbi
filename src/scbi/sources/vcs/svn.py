"""Subversion (port of svn-co, svn-branch and the subversion cases of
get-vcs-commit-id, get-vcs-ref and vcs-build-id).

Only the standard layout (trunk, branches, tags at the root) is
supported: svn-branch links ``src`` into the checkout.
"""

from __future__ import annotations

import os
import re
import subprocess

from scbi.bashcompat import words
from scbi.sources.vcs.base import Vcs, VcsRun


class Subversion(Vcs):
    names = ("svn", "subversion")
    label = "subversion"
    id_kind = "revision"
    default_ref = "trunk"
    tool = "svn"
    marker = ".svn"

    def checkout(self, r: VcsRun, url: str, options: str, name: str, dir: str) -> int:
        url = url[:-1] if url.endswith("/") else url
        repo = dir or url.rsplit("/", 1)[-1]
        os.makedirs(f"{r.bdir}/.vcs", exist_ok=True)
        if not r.cd(f"{r.bdir}/.vcs"):
            return 1
        if not r.isdir(repo):
            res = r.run("svn", "co", *words(url), *words(repo))
        else:
            r.cd(repo)
            if not r.isdir(".svn"):
                r.logger.ilog("build", "error:", *words(r.cwd), "not", "a", "subversion", "repository")
                return 1
            res = r.run("svn", "update")
        if res != 0:
            return res
        if not r.cd(f"{r.bdir}/{name}"):
            return 1
        return r.run("ln", "-s", f"../.vcs/{repo}", "vcs")

    def branch(self, r: VcsRun, options: str, module: str, branch: str, dir: str,
               *, fetch: bool = True) -> int:
        r.cd(f"{r.bdir}/{module}")
        d = r.isdir
        if branch == "NONE":
            if dir and d(f"vcs/trunk/{dir}"):
                target = f"vcs/trunk/{dir}"
            elif d("vcs/trunk"):
                target = "vcs/trunk"
            else:
                target = "vcs"
        elif dir and d(f"vcs/branches/{branch}/{dir}"):
            target = f"vcs/branches/{branch}/{dir}"
        elif dir and d(f"vcs/branches/{dir}/{branch}"):
            target = f"vcs/branches/{dir}/{branch}"
        elif d(f"vcs/branches/{branch}"):
            target = f"vcs/branches/{branch}"
        elif dir and d(f"vcs/tags/{branch}/{dir}"):
            target = f"vcs/tags/{branch}/{dir}"
        elif dir and d(f"vcs/tags/{dir}/{branch}"):
            target = f"vcs/tags/{dir}/{branch}"
        elif d(f"vcs/tags/{branch}"):
            target = f"vcs/tags/{branch}"
        else:
            r.logger.ilog("build", f"error: switching subversion branch {branch}")
            return 1
        return r.run("ln", "-s", *words(target), "src")

    def link_src(self, r: VcsRun, module: str, ref: str) -> int:
        #  svn-branch "" "" $module $ref "": output to the console
        return self.branch(r, "", module, ref, "")

    def commit_id(self, short: bool, dir: str, env: dict[str, str]) -> str:
        proc = subprocess.run(["svn", "log", "-l", "1", f"{dir}/../src"], env=env,
                              stdin=subprocess.DEVNULL, capture_output=True)
        ids = [line.split(" ", 1)[0] for line in proc.stdout.decode(errors="surrogateescape").split("\n")
               if re.match(r"^r[0-9]", line)]
        return "\n".join(ids)

    def source_id(self, r: VcsRun) -> str:
        env = dict(r.env, LANG="C")
        proc = subprocess.run(["svn", "info"], cwd=r.cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True)
        revs = [m.group(1) for m in re.finditer(r"(?m)^Revision: ([0-9]*).*$",
                                                proc.stdout.decode(errors="surrogateescape"))]
        return "r" + "\n".join(revs)
