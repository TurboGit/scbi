"""Build identifiers (sources/buildid.py) compared with the Bash
functions."""

import pytest

from probe import probe_pair

VARIANTS = ["default", "v1", "v2", "agg", "one", "two", "native"]
MODULES = ["lib1", "lib2", "dmain", "metaagg3", "mainmult", "dep1", "lib3", "dmod", "cd1", "listDA", "metaagg3/agg", "lib1:skip", "lib2/v1",
                   "libinh1", "child", "multpatch", "patches", "nothere"]


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory):
    bash, python = probe_pair(tmp_path_factory.mktemp("buildid"))
    #  a build id for every module (a missing one is replaced by the
    #  current time)
    for sb in (bash, python):
        for plugin in (sb.root / "scripts.d").iterdir():
            if plugin.is_file() and not plugin.name.startswith((".", "_")) and not plugin.name[0].isdigit():
                d = sb.root / ".root" / "builds" / plugin.name
                d.mkdir(parents=True, exist_ok=True)
                for v in VARIANTS:
                    (d / f"build-id-{v}").write_text(f"bid-{plugin.name}-{v}\n")
        #  a patch in SCBI_PATCH and one in the plug-ins' patches directory
        (sb.root / ".root" / ".patches").mkdir(parents=True, exist_ok=True)
        (sb.root / ".root" / ".patches" / "lib1-0-fix.patch").write_text("--- a\n+++ b\n")
        (sb.root / "scripts.d" / "patches").mkdir(exist_ok=True)
        (sb.root / "scripts.d" / "patches" / "fix.diff").write_text("--- c\n+++ d\n")
    return bash, python


def cmds(env_vid="vid1"):
    c = []
    for m in MODULES:
        c += ["build-id", "@root", m, env_vid, "@@", "depends-build-id", m, "@@"]
    for p in ("multpatch-1.diff", "nothere.diff", "fix.diff", "lib1-0-fix.patch"):
        c += ["patch-md5", p, "@@"]
    return c


@pytest.mark.oracle
@pytest.mark.parametrize("opts", [[], ["--patch"], ["--no-patch"]], ids=["default", "patch", "no-patch"])
def test_build_id_same_as_bash(sandboxes, opts):
    bash, python = sandboxes
    args = [*opts, "probe", *cmds()]
    env = {"SCBI_CMAKE_BUILD_TYPE": "Debug", "SCBI_lib2_BUILD_TYPE": "Release"}
    rb, rp = bash.run(args, env), python.run(args, env)
    assert "rc=0 " in rb.stdout and "not-found" in rb.stdout
    assert rb.stdout.count("not-found") < 3
    lb, lp = rb.stdout.splitlines(), rp.stdout.splitlines()
    for i, (x, y) in enumerate(zip(lb, lp)):
        assert y == x, f"line {i}: {x}"
    assert (rp.returncode, len(lp), rp.stderr) == (rb.returncode, len(lb), rb.stderr)
