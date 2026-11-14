"""The vcs/archive hook data (sources/data.py) compared with the Bash
functions, for every plug-in and variant (test and real plug-ins)."""

import re
import subprocess

import pytest

from oracle import REPO_ROOT
from probe import probe_pair

FUNC = re.compile(r"(?m)^\s*(?:function\s+)?([A-Za-z0-9_.+@-]+)\s*\(\)")


def plugin_variants(directory, converted):
    """(plug-in, variant) of the Bash plug-ins of ``directory`` which have a
    YAML version in ``converted`` (the plug-ins of the Python driver)."""
    result = []
    for f in sorted(directory.iterdir()):
        if not f.is_file() or f.name.startswith((".", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "_")):
            continue
        if f.name.endswith(("~", ".yaml", ".diff")):
            continue
        if not (converted / f"{f.name}.yaml").is_file():
            continue
        if subprocess.run(["bash", "-n", str(f)], capture_output=True).returncode != 0:
            continue  # broken on purpose (fixtures of lint/format)
        names = FUNC.findall(f.read_text(errors="replace"))
        variants = {"default", "native"}
        for n in names:
            m = re.match(re.escape(f.name) + r"-(.+?)-(?:cross-)?(?:vcs|archive)$", n)
            if m:
                variants.add(m.group(1))
        result += [(f.name, v) for v in sorted(variants)]
    return result


def commands(pairs):
    cmds = []
    for module, variant in pairs:
        cmds += ["vcs-data", module, variant, "@@",
                 "archive-data", module, variant, "1.2", "@@",
                 "archive-exists", module, variant, "1", "@@",
                 "vcs-dir", module, "@@",
                 "vcs-dir", f"{module}:dev", "@@"]
    return cmds


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory):
    return probe_pair(tmp_path_factory.mktemp("srcdata"))


def compare(sandboxes, args):
    bash, python = sandboxes
    rb, rp = bash.run(args), python.run(args)
    lb, lp = rb.stdout.splitlines(), rp.stdout.splitlines()
    for i, (x, y) in enumerate(zip(lb, lp)):
        assert y == x, f"line {i}"
    assert (rp.returncode, len(lp), rp.stderr) == (rb.returncode, len(lb), rb.stderr)


def chunks(pairs, size=60):
    #  one driver run per chunk
    return [pairs[i:i + size] for i in range(0, len(pairs), size)]


@pytest.mark.oracle
def test_data_test_plugins(sandboxes):
    plugins = sandboxes[0].root / "scripts.d"
    for chunk in chunks(plugin_variants(plugins, sandboxes[1].root / "scripts.d")):
        compare(sandboxes, ["probe", *commands(chunk)])


@pytest.mark.oracle
def test_data_real_plugins(sandboxes, tmp_path):
    import shutil

    from e2e import convert_dir

    plugins = REPO_ROOT / "scripts.d"
    converted = tmp_path / "scripts.d"
    shutil.copytree(plugins, converted, ignore=shutil.ignore_patterns("*.yaml", "*~"))
    convert_dir(converted)
    bash, python = sandboxes
    #  the settings of the real 1_setup (not those of the testsuite)
    root = f"{python.root}/home/dev"
    env = {"SCBI_ROOT": root, "SCBI_ARCHIVES": "", "SCBI_PATCH": "",
           "SCBI_GIT_REPO": f"{root}/repositories/git", "SCBI_SVN_REPO": f"{root}/repositories/svn",
           "SCBI_HG_REPO": f"{root}/repositories/hg"}
    for chunk in chunks(plugin_variants(plugins, converted)):
        args = ["probe", *commands(chunk)]
        rb, rp = bash.run([f"--plugins={plugins}", *args]), python.run([f"--plugins={converted}", *args], env)
        lb, lp = rb.stdout.splitlines(), rp.stdout.splitlines()
        for i, (x, y) in enumerate(zip(lb, lp)):
            assert y == x.replace(str(plugins), str(converted)), f"line {i}"
        assert (rp.returncode, len(lp)) == (rb.returncode, len(lb))


@pytest.mark.oracle
def test_data_variant_selection(sandboxes):
    plugins = sandboxes[0].root / "scripts.d"
    pairs = plugin_variants(plugins, sandboxes[1].root / "scripts.d")
    for env in ({"SCBI_VCS_VARIANT": "vcs", "SCBI_ARCHIVE_VARIANT": "vcs"},
                {"SCBI_lib1_VCS_VARIANT": "nope", "SCBI_lib1_ARCHIVE_VARIANT": "nope"}):
        bash, python = sandboxes
        args = ["probe", *commands(pairs[:60])]
        rb, rp = bash.run(args, env), python.run(args, env)
        assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), env
