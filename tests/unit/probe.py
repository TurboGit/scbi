"""Sandboxes with the test-only ``probe`` sub-command (see probe_tool)."""

import os
import subprocess
import sys

from e2e import pair
from oracle import REPO_ROOT
from probe_tool import PROBE_SCRIPT

PY_DRIVER = """#!/bin/bash
SCBI_ARGV0="$0" PYTHONPATH={src}:{unit} exec python3 -c '
import runpy, scbi.tools
scbi.tools.TOOLS["probe"] = "probe_tool"
runpy.run_module("scbi", run_name="__main__")' "$@"
"""


def to_yaml(sandbox):
    """Convert the plug-ins of a sandbox to YAML, as tests/run does with
    SCBI_PLUGIN_FORMAT=yaml (the plug-ins that do not convert stay Bash)."""
    plugins = sandbox.root / "scripts.d"
    sources = [str(f) for f in sorted(plugins.iterdir())
               if f.is_file() and not f.name.startswith(("_", ".")) and not f.name[0].isdigit()
               and not f.name.endswith(("~", ".yaml"))]
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    for args in (["--output-dir", str(plugins), *sources], ["--closure", str(plugins)]):
        subprocess.run([sys.executable, "-m", "scbi.convert", *args], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def probe_pair(tmp_path, yaml=False):
    """Bash and Python sandboxes; with ``yaml`` the Python one uses the YAML
    versions of the plug-ins."""
    bash, python = pair(tmp_path)
    if yaml:
        to_yaml(python)
    for sb in (bash, python):
        tool = sb.root / "scbi-probe"
        tool.write_text(PROBE_SCRIPT)
        tool.chmod(0o755)
    (python.root / "scbi").write_text(PY_DRIVER.format(src=REPO_ROOT / "src", unit=REPO_ROOT / "tests" / "unit"))
    return bash, python


def same(bash, python, args, env=None):
    rb, rp = bash.run(args, env), python.run(args, env)
    assert (rp.returncode, rp.stdout, rp.stderr) == (rb.returncode, rb.stdout, rb.stderr), args
