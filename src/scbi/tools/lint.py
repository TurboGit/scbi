"""scbi lint: checks of YAML plug-ins (scbi.plugin.lint).

Bash plug-ins are not checked: they are converted to YAML once with
``python3 -m scbi.convert``.
"""

from __future__ import annotations

import subprocess
import sys

import yaml

from scbi.bashcompat import words
from scbi.plugin import yamlfmt
from scbi.plugin.lint import ERROR, dependency_vars, lint_text
from scbi.tools.plugins import display, resolve

USAGE = """
SCBI-LINT {version}

{argv0} lint [options] plug-in1 [plug-in2...]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --plugins=<dir>    specify the plugins' directory
      | --error            report only errors
      | --stat             display some status of current setup

Checks YAML plug-ins (<name>.yaml): unknown hooks and keys, structure and
values, conditions, environment actions; warnings for empty hooks and
variables not known in a hook."""


def main(driver, args: list[str]) -> int:
    proc = subprocess.run(["getopt", "-u", "-o", "ehv", "-l", "error,help,version,plugins:",
                           "--", *words(" ".join(args))],
                          capture_output=True, text=True, env=driver.base_env())
    warnings = True
    for a in words(proc.stdout):
        if a == "--error":
            warnings = False

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 1

    status = 0
    for name in words(" ".join(driver.modules)):
        path, reason = resolve(driver, name)
        if path is None:
            print()
            print(f"========== Skip {name}: {reason}")
            if reason != "not found":
                status = 1
            continue
        if warnings:
            print()
            print(f"========== Handle {display(driver, path)}")
        plugin = path.name[: -len(".yaml")]
        text = path.read_text(errors="replace")
        #  the variables given to the hooks by the environment file and by
        #  the plug-ins used (env of the dependencies, inherited plug-ins)
        known = frozenset(driver.envfile.settings) | frozenset(driver.envfile.passthrough)
        try:
            data = yaml.load(text, Loader=yamlfmt._Loader)
        except yaml.YAMLError:
            data = None
        if isinstance(data, dict):
            known |= dependency_vars(plugin, data, lambda n: resolve(driver, n)[0])
        for issue in lint_text(plugin, text, str(path), known):
            if issue.level == ERROR:
                print(f"   error:   ({issue.where}) {issue.message}")
                status = 1
            elif warnings:
                print(f"   warning: ({issue.where}) {issue.message}")
    sys.stdout.flush()
    return status
