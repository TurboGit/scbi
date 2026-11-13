"""The dependency walker (walker.py) compared with the Bash
``for-all-modules*`` functions, through a test-only sub-command."""

import pytest

from e2e import pair
from oracle import REPO_ROOT
from scbi.walker import ENTRY_POINTS

BASH_TOOL = """#!/bin/bash
[[ $1 == subcommand ]] && shift
cb() { echo "CB $*"; }
${SCBI_MODULES[0]} cb ${SCBI_MODULES[1]} x1 x2
echo "rc=$?"
"""

PY_DRIVER = """#!/bin/bash
SCBI_ARGV0="$0" PYTHONPATH={src}:{unit} exec python3 -c '
import runpy, scbi.tools
scbi.tools.TOOLS["walk"] = "walk_tool"
runpy.run_module("scbi", run_name="__main__")' "$@"
"""

MODULES = ["supermod", "dmain", "listDA", "reca", "cd1", "cdb", "lib1", "meta-meta/both:v2",
           "lib2", "dmod", "nothere", "lib1:skip"]


@pytest.fixture(scope="module")
def sandboxes(tmp_path_factory):
    bash, python = pair(tmp_path_factory.mktemp("walk"))
    for sb in (bash, python):
        tool = sb.root / "scbi-walk"
        tool.write_text(BASH_TOOL)
        tool.chmod(0o755)
    (python.root / "scbi").write_text(PY_DRIVER.format(src=REPO_ROOT / "src", unit=REPO_ROOT / "tests" / "unit"))
    return bash, python


@pytest.mark.oracle
@pytest.mark.parametrize("entry", sorted(ENTRY_POINTS))
@pytest.mark.parametrize("modref", MODULES)
def test_walker_same_as_bash(sandboxes, entry, modref):
    bash, python = sandboxes
    args = ["--plan=meta-meta"] if modref.startswith("meta-meta") else []
    args += ["walk", entry, modref]
    rb, rp = bash.run(args), python.run(args)
    assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr)

