"""The vcs/archive hook data (sources/data.py) compared with the Bash
functions, for every plug-in and variant (test and real plug-ins)."""

import re
import subprocess

import pytest

from oracle import REPO_ROOT
from probe import probe_pair

FUNC = re.compile(r"(?m)^\s*(?:function\s+)?([A-Za-z0-9_.+@-]+)\s*\(\)")


def plugin_variants(directory):
    result = []
    for f in sorted(directory.iterdir()):
        if not f.is_file() or f.name.startswith((".", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "_")):
            continue
        if f.name.endswith(("~", ".yaml", ".diff")):
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
    #  one driver run per chunk: a hook shell sources all the loaded
    #  plug-ins, so loading every plug-in in one run is slow
    return [pairs[i:i + size] for i in range(0, len(pairs), size)]


@pytest.mark.oracle
def test_data_test_plugins(sandboxes):
    plugins = sandboxes[0].root / "scripts.d"
    for chunk in chunks(plugin_variants(plugins)):
        compare(sandboxes, ["probe", *commands(chunk)])


@pytest.mark.oracle
def test_data_real_plugins(sandboxes):
    plugins = REPO_ROOT / "scripts.d"
    for chunk in chunks(plugin_variants(plugins)):
        compare(sandboxes, [f"--plugins={plugins}", "probe", *commands(chunk)])


@pytest.mark.oracle
def test_data_variant_selection(sandboxes):
    plugins = sandboxes[0].root / "scripts.d"
    pairs = plugin_variants(plugins)
    for env in ({"SCBI_VCS_VARIANT": "vcs", "SCBI_ARCHIVE_VARIANT": "vcs"},
                {"SCBI_lib1_VCS_VARIANT": "nope", "SCBI_lib1_ARCHIVE_VARIANT": "nope"}):
        bash, python = sandboxes
        args = ["probe", *commands(pairs[:60])]
        rb, rp = bash.run(args, env), python.run(args, env)
        assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), env


REDEF = """
function get-vcs-data() { echo user none none git http://redefined/$1.git; }
function get-archive-data() { echo user none none cp /x $1-$3.tgz; return 3; }
function check-archive-exists() { echo "never shown"; return 0; }
function get-vcs-dir() { echo /user/$1; }
"""


@pytest.mark.oracle
def test_data_redefined_uses_bash(sandboxes):
    """A user redefinition of a ported function (here in a runtime file
    sourced after the reference one) is used instead of the Python port."""
    bash, python = sandboxes
    args = ["probe", *commands([("lib1", "default"), ("lib2", "default")])]
    try:
        for sb in sandboxes:
            (sb.root / "scripts.d" / "9_zredef").write_text(REDEF)
        rb, rp = bash.run(args), python.run(args)
    finally:
        for sb in sandboxes:
            (sb.root / "scripts.d" / "9_zredef").unlink()
    assert "redefined" in rb.stdout
    assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr)
