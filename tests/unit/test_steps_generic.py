"""The generic module steps (steps/generic.py) compared with the Bash
functions of scripts.d/7_modgen, on a sequence of steps sharing the
sandboxes: setup (sources synchronized, patches applied or missing, out
of tree or not, no sources), install (manifest, ids copied, build id
computed), pre-install (files of the manifest removed from the
installation prefix) and purge."""

from pathlib import Path

import pytest

from probe import probe_pair
from test_sources_handle import mask, setup_repos, tree

#  (probe arguments, action before)
STEPS = [
    (["handle-sources", "@root", "lib1"], None),
    (["generic", "setup", "@root", "lib1", "false"], None),            # no target directory
    (["generic", "setup", "@root", "lib1", "false"], "tvdir lib1 default"),
    (["generic", "setup", "@root", "lib1", "true"], None),
    (["generic", "install", "@root", "lib1", "true"], "installed"),
    (["generic", "pre-install", "@root", "lib1", "true"], "prefix"),
    (["generic", "install", "@root", "lib1", "true"], "no-build-id"),
    (["generic", "purge", "@root", "lib1", "true"], None),
    (["handle-sources", "@root", "withpatch"], None),
    (["generic", "setup", "@root", "withpatch", "false"], "tvdir withpatch default"),
    (["generic", "setup", "@root", "withpatch/var", "true"], "tvdir withpatch var"),
    (["generic", "setup", "@root", "dep1", "false"], "tvdir dep1 default"),
    (["generic", "install", "@root", "dep1", "false"], None),
]


def act(root: Path, action: str | None) -> None:
    builds = root / ".root" / "builds"
    tv = builds / "lib1" / "x86_64-linux-gnu-default"
    if action and action.startswith("tvdir"):
        _, module, variant = action.split()
        (builds / module / f"x86_64-linux-gnu-{variant}").mkdir(parents=True, exist_ok=True)
    elif action == "installed":
        for f in ("bin/tool", "lib/libx.a", "share/doc/x/README"):
            p = tv / "install" / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f + "\n")
        (tv / "install" / "lib" / "link.a").symlink_to("libx.a")
    elif action == "prefix":
        prefix = root / "prefix"
        for f in ("bin/tool", "lib/libx.a", "lib/other.a", "share/doc/x/README"):
            p = prefix / f
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n")
    elif action == "no-build-id":
        (builds / "lib1" / "build-id-default").unlink()


@pytest.mark.oracle
def test_generic_steps_same_as_bash(tmp_path):
    repos = setup_repos(tmp_path)
    bash, python = probe_pair(tmp_path / "sb")
    for sb in (bash, python):
        patches = sb.root / ".root" / ".patches"
        patches.mkdir(parents=True, exist_ok=True)
        (patches / "withpatch-com-fix.patch").write_text(
            "--- a/lib1.c\n+++ b/lib1.c\n@@ -1 +1 @@\n-nothing\n+x\n")
    for i, (args, action) in enumerate(STEPS):
        for sb in (bash, python):
            act(sb.root, action)
        env = {"TESTREPOS": str(repos), "GIT_ALLOW_PROTOCOL": "file", "DO_UPDATE": "no",
               "SCBI_PREFIX": str(Path("<root>") / "prefix")}
        rb = bash.run(["probe", *args], {**env, "SCBI_PREFIX": str(bash.root / "prefix")})
        rp = python.run(["probe", *args], {**env, "SCBI_PREFIX": str(python.root / "prefix")})
        ctx = f"step {i}: {args}"
        assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), ctx
        module = args[3].split("/")[0] if args[0] == "generic" else args[2]
        bb, pb = bash.root / ".root" / "builds", python.root / ".root" / "builds"
        blog, plog = bb / f"{module}.log", pb / f"{module}.log"
        assert mask(plog.read_text() if plog.exists() else "", python.root) == \
            mask(blog.read_text() if blog.exists() else "", bash.root), ctx
        #  the build ids computed without sources depend on the time
        time_ids = module == "dep1"
        assert [mask(x, python.root) for x in tree(pb / module, time_ids)] == \
            [mask(x, bash.root) for x in tree(bb / module, time_ids)], ctx
        assert tree(python.root / "prefix") == tree(bash.root / "prefix"), ctx
