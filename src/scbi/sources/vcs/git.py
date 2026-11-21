"""Git (port of git-co, git-set-submodule-url, git-branch and the git
cases of get-vcs-commit-id, get-vcs-ref and vcs-build-id)."""

from __future__ import annotations

import hashlib
import os
import subprocess

from scbi.bashcompat import words
from scbi.sources.vcs.base import Vcs, VcsRun, option_list

BUILD_BRANCH = "scbi"


def _basename(url: str, suffix: str = "") -> str:
    """``basename URL SUFFIX``."""
    name = os.path.basename(url.rstrip("/")) if url.strip("/") else ("/" if url else "")
    if suffix and name.endswith(suffix) and name != suffix:
        name = name[: -len(suffix)]
    return name


def set_submodule_url(r: VcsRun, options: str) -> None:
    """``git-set-submodule-url OPTIONS``: options ``submodule:PATH:URL``."""
    for o in option_list(options):
        cmd = o.split(":", 1)[0]
        if cmd != "submodule":
            continue
        so = o[len("submodule:"):] if o.startswith("submodule:") else o
        pth = so.split(":", 1)[0]
        url = so.split(":", 1)[1] if ":" in so else so
        if r.run("git", "submodule", "set-url", *words(pth), *words(url)) != 0:
            #  maybe a too old version without set-url
            r.run("sed", "-i", "-z", f"s,\\({pth}.*url = \\)\\(.*\\),\\1{url}\\n,g", ".gitmodules", ".git/config")


class Git(Vcs):
    names = ("git",)
    label = "git"
    id_kind = "sha-1"
    default_ref = "master"
    tool = "git"
    marker = ".git"

    def checkout(self, r: VcsRun, url: str, options: str, name: str, dir: str) -> int:
        repo = dir or _basename(url, ".git")
        lopts = option_list(options)
        #  HAS_LFS is set to "true" but tested against "yes" in Bash: the
        #  lfs fetch is never done
        recursive = "no-recursive" not in lopts
        gopts1 = ["--recursive"] if recursive else []
        gopts2 = ["--recurse-submodules"] if recursive else []

        os.makedirs(f"{r.bdir}/.vcs", exist_ok=True)
        if not r.cd(f"{r.bdir}/.vcs"):
            return 1
        if not r.isdir(repo):
            res = r.run("git", "clone", *words(url), *words(repo))
            if res == 0:
                if not r.cd(repo):
                    res = 1
                elif r.isfile(".gitmodules"):
                    set_submodule_url(r, options)
                    r.run("git", "submodule", "init")
                    res = r.run("git", "submodule", "update", *gopts1)
        else:
            r.cd(repo)
            if not r.isdir(".git"):
                r.logger.ilog("build", "error:", *words(r.cwd), "not", "a", "git", "repository")
                return 1
            #  the URL is set in case the repository has been relocated
            r.run("git", "remote", "set-url", "origin", *words(url))
            res = 0
            if r.isfile(".gitmodules"):
                set_submodule_url(r, options)
                res = r.run("git", "submodule", "update", *gopts1)
            if res == 0:
                res = r.run("git", "fetch", "origin", "--force", "--tags", *gopts2)
        if res != 0:
            return res
        if not r.cd(f"{r.bdir}/{name}"):
            return 1
        return r.run("ln", "-s", f"../.vcs/{repo}", "vcs")

    def branch(self, r: VcsRun, options: str, module: str, branch: str, dir: str,
               *, fetch: bool = True) -> int:
        r.cd(f"{r.bdir}/{module}/vcs")
        r.run("git", "checkout", "--force", "master")
        if fetch:
            r.run("git", "fetch", "origin", "--tags")

        if branch == "NONE":
            _, defbr = r.output("git", "rev-parse", "--abbrev-ref", "origin/HEAD")
            branch = defbr[len("origin/"):] if defbr.startswith("origin/") else defbr

        #  only an exit status of 1 means "not found"
        if r.run("git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}") == 1:
            if r.run("git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}") == 1:
                if r.run("git", "show-ref", "--verify", "--quiet", f"refs/tags/{branch}") == 1:
                    rc = subprocess.run(["git", "rev-parse", "-q", "--verify", f"{branch}^{{commit}}"],
                                        cwd=r.cwd, env=r.env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
                    if rc == 1:
                        r.logger.ilog("build", "error: switching git branch")
                        return 1
                br = branch
            else:
                br = f"refs/heads/{branch}"
        else:
            br = f"refs/remotes/origin/{branch}"

        if r.run("git", "show-ref", "--verify", "--quiet", f"refs/heads/{BUILD_BRANCH}") == 1:
            r.run("git", "branch", BUILD_BRANCH)

        r.run("git", "checkout", BUILD_BRANCH)
        _, cur = r.output("git", "rev-parse", "--short", "HEAD")
        r.run("git", "reset", "--hard", *words(br))
        _, new = r.output("git", "rev-parse", "--short", "HEAD")

        if cur != new:
            r.mail(f"scbi: {module} updated {cur}..{new}")
            r.logger.ilog(module, f"scbi: {module} updated {cur}..{new}")

        if f",{options}," == f",{options},".replace(",no-recursive,", "", 1) and r.isfile(".gitmodules"):
            set_submodule_url(r, options)
            return r.run("git", "submodule", "update", "--force", "--init", "--recursive")
        return 0

    def commit_id(self, short: bool, dir: str, env: dict[str, str]) -> str:
        args = ["git", "--git-dir", f"{dir}/.git", "rev-parse"]
        args += ["--short=6", "HEAD"] if short else ["HEAD"]
        proc = subprocess.run(args, env=env, stdin=subprocess.DEVNULL, capture_output=True)
        return proc.stdout.decode(errors="surrogateescape").rstrip("\n")

    def source_id(self, r: VcsRun) -> str:
        def out(*args: str) -> bytes:
            return subprocess.run(list(args), cwd=r.cwd, env=r.env, stdin=subprocess.DEVNULL,
                                  capture_output=True).stdout

        gver = out("git", "rev-list", "-1", "HEAD", "--").decode(errors="surrogateescape").rstrip("\n")
        diff = out("git", "diff", "HEAD", "--") + out(
            "git", "submodule", "--quiet", "foreach", "--recursive", "git", "diff", "HEAD", "--")
        return gver + hashlib.md5(diff).hexdigest()
