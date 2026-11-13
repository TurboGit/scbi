"""Git support (sources/vcs/git.py) compared with git-co / git-branch /
get-vcs-commit-id and the git part of vcs-build-id (scripts.d/4_scm):
same exit statuses, same checkouts, same module log."""

import re
import subprocess
from pathlib import Path

import pytest

from oracle import BashOracle
from scbi.log import Logger
from scbi.sources.vcs import registry
from scbi.sources.vcs.base import VcsRun

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@e", "-c", "protocol.file.allow=always"]


def make_repos(root: Path) -> dict[str, str]:
    """A repository with branches, a tag and a few commits; one with a
    submodule."""
    def git(cwd, *args):
        subprocess.run([*GIT, *args], cwd=cwd, check=True, capture_output=True)

    lib = root / "lib"
    lib.mkdir(parents=True)
    git(lib, "init", "-b", "master")
    (lib / "a.txt").write_text("1\n")
    git(lib, "add", "a.txt")
    git(lib, "commit", "-m", "c1")
    git(lib, "tag", "v1.0")
    git(lib, "branch", "v1")
    (lib / "a.txt").write_text("2\n")
    git(lib, "commit", "-am", "c2")
    first = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=lib,
                           capture_output=True, text=True).stdout.strip()

    sub = root / "sub"
    sub.mkdir()
    git(sub, "init", "-b", "master")
    (sub / "s.txt").write_text("sub\n")
    git(sub, "add", "s.txt")
    git(sub, "commit", "-m", "s1")
    main = root / "main"
    main.mkdir()
    git(main, "init", "-b", "master")
    (main / "m.txt").write_text("main\n")
    git(main, "add", "m.txt")
    git(main, "submodule", "add", str(sub), "subm")
    git(main, "commit", "-m", "m1")
    return {"lib": str(lib), "main": str(main), "first": first}


#  (operation, module, argument): co URL OPTIONS | br REF OPTIONS | id | rmvcs | touch
def scenario(repos):
    return [
        ("co", "lib", repos["lib"], "none"),
        ("br", "lib", "NONE", "none"), ("id", "lib"),
        ("br", "lib", "v1", "none"), ("id", "lib"),
        ("br", "lib", "v1.0", "none"), ("id", "lib"),
        ("br", "lib", repos["first"], "none"), ("id", "lib"),
        ("br", "lib", "nothere", "none"), ("id", "lib"),
        ("br", "lib", "master", "none"), ("id", "lib"),
        ("touch", "lib"), ("id", "lib"),
        ("rmvcs", "lib"), ("co", "lib", repos["lib"], "none"), ("id", "lib"),
        ("co", "main", repos["main"], "none"), ("br", "main", "NONE", "none"), ("id", "main"),
        ("rmvcs", "main"), ("co", "main", repos["main"], "no-recursive"),
        ("br", "main", "master", "no-recursive"), ("id", "main"),
        ("co", "bad", "/nothere/repo.git", "none"),
    ]


def bash_script(steps, vcs="git") -> str:
    lines = ['log=$SCBI_BDIR/../module.log', 'export GIT_ALLOW_PROTOCOL=file']
    for step in steps:
        op, module = step[0], step[1]
        lines.append(f"mkdir -p $SCBI_BDIR/{module}")
        if op == "co":
            lines.append(f'(cd $SCBI_BDIR/{module}; {vcs}-co none {step[2]} {step[3]} {module} "" >> $log 2>&1; echo "co $?")')
        elif op == "br":
            lines.append(f'{vcs}-branch none {step[3]} {module} {step[2]} "{step[4] if len(step) > 4 else ''}" >> $log 2>&1; echo "br $?"')
        elif op == "id":
            lines.append(f"echo \"id $(get-vcs-commit-id true {vcs} $SCBI_BDIR/{module}/vcs) "
                         f"$(get-vcs-commit-id false {vcs} $SCBI_BDIR/{module}/vcs)\"")
            lines.append(SOURCE_ID[vcs].format(module=module))
        elif op == "rmvcs":
            lines.append(f"rm -f $SCBI_BDIR/{module}/vcs $SCBI_BDIR/{module}/src")
        elif op == "touch":
            lines.append(f"echo change >> $SCBI_BDIR/{module}/vcs/a.txt")
    return "\n".join(lines)


#  the part of vcs-build-id for each VCS
SOURCE_ID = {
    "git": ("(cd $SCBI_BDIR/{module}/vcs; gver=$(git rev-list -1 HEAD --); "
            "gdif=$( ( git diff HEAD -- ; git submodule --quiet foreach --recursive "
            "git diff HEAD -- ) | get-md5 ); echo \"sid $gver$gdif\")"),
    "svn": ("(cd $SCBI_BDIR/{module}/vcs; echo \"sid r$(LANG=C svn info | "
            "sed -n -e '/^Revision: \\([0-9]*\\).*$/s//\\1/p')\")"),
    "hg": ("(cd $SCBI_BDIR/{module}/vcs; hver=$(hg identify --num); "
           "hdif=$(hg diff | tail -n+4 | get-md5); echo \"sid $hver$hdif\")"),
}


def python_run(steps, bdir: Path, logs: Path, vcs="git") -> list[str]:
    import os

    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(bdir.parent / "home"),
           "LANG": "C", "LC_ALL": "C", "GIT_ALLOW_PROTOCOL": "file"}
    git = registry.get(vcs)
    (logs / "today").mkdir(parents=True, exist_ok=True)
    logger = Logger(logs, "today", "tgt", bdir.parent / "sep")
    out = []
    with open(bdir.parent / "module.log", "a") as log:
        for step in steps:
            op, module = step[0], step[1]
            (bdir / module).mkdir(parents=True, exist_ok=True)
            r = VcsRun.to_log(env, str(bdir), log, logger, lambda m: None)
            r.cwd = str(bdir / module)
            if op == "co":
                out.append(f"co {git.checkout(r, step[2], step[3], module, '')}")
            elif op == "br":
                out.append(f"br {git.branch(r, step[3], module, step[2], step[4] if len(step) > 4 else '')}")
            elif op == "id":
                vcs = f"{bdir}/{module}/vcs"
                out.append(f"id {git.commit_id(True, vcs, env)} {git.commit_id(False, vcs, env)}")
                r.cd(vcs)
                out.append(f"sid {git.source_id(r)}")
            elif op == "rmvcs":
                Path(bdir, module, "vcs").unlink(missing_ok=True)
                Path(bdir, module, "src").unlink(missing_ok=True)
            elif op == "touch":
                with open(bdir / module / "vcs" / "a.txt", "a") as f:
                    f.write("change\n")
    return out


def mask(text: str, root: Path) -> str:
    text = re.sub(r"\d{4}/\d\d/\d\d \d\d:\d\d:\d\d", "<ts>", text)
    return text.replace(str(root), "<root>")


@pytest.mark.oracle
def test_git_same_as_bash(tmp_path):
    repos = make_repos(tmp_path / "repos")
    steps = scenario(repos)

    bw = tmp_path / "bash"
    oracle = BashOracle(bw)
    bdir = bw / "bdir"
    bdir.mkdir()
    env = {"SCBI_BDIR": str(bdir), "SCBI_LOGS": str(bw / "logs"), "TODAY": "today", "SCBI_TARGET": "tgt"}
    rb = oracle.run(bash_script(steps), env, check=False)
    bash_out = rb.stdout.splitlines()

    pw = tmp_path / "python"
    pbdir = pw / "bdir"
    pbdir.mkdir(parents=True)
    py_out = python_run(steps, pbdir, pw / "logs")

    assert py_out == bash_out
    assert "br 1" in bash_out and "co 128" in bash_out
    blog = mask((bw / "module.log").read_text(), bw)
    plog = mask((pw / "module.log").read_text(), pw)
    assert plog == blog
    for m in ("lib", "main"):
        state = ["git", "-C", "{}/bdir/" + m + "/vcs", "status", "--porcelain=v1", "--branch"]
        sb = subprocess.run([s.format(bw) for s in state], capture_output=True, text=True).stdout
        sp = subprocess.run([s.format(pw) for s in state], capture_output=True, text=True).stdout
        assert sp == sb
