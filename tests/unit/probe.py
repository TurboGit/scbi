"""Sandboxes with the test-only ``probe`` sub-command (see probe_tool)."""

from e2e import pair
from oracle import REPO_ROOT
from probe_tool import PROBE_SCRIPT

PY_DRIVER = """#!/bin/bash
SCBI_ARGV0="$0" PYTHONPATH={src}:{unit} exec python3 -c '
import runpy, scbi.tools
scbi.tools.TOOLS["probe"] = "probe_tool"
runpy.run_module("scbi", run_name="__main__")' "$@"
"""


def probe_pair(tmp_path):
    bash, python = pair(tmp_path)
    for sb in (bash, python):
        tool = sb.root / "scbi-probe"
        tool.write_text(PROBE_SCRIPT)
        tool.chmod(0o755)
    (python.root / "scbi").write_text(PY_DRIVER.format(src=REPO_ROOT / "src", unit=REPO_ROOT / "tests" / "unit"))
    return bash, python


def same(bash, python, args, env=None):
    rb, rp = bash.run(args, env), python.run(args, env)
    assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), args
