"""scbi lint: checks of YAML plug-ins (scbi.plugin.lint).

Bash plug-ins are not checked: they are converted to YAML once with
``python3 -m scbi.convert``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
      | --json             report as JSON (for the editors)
      | --stdin            the text of the (single) plug-in from the
                           standard input (e.g. an unsaved buffer)
      | --stat             display some status of current setup

Checks YAML plug-ins (<name>.yaml): unknown hooks and keys, structure and
values, conditions, environment actions; warnings for empty hooks and
variables not known in a hook.

With --json the output is a JSON list of the issues, each one an object
with the keys file, line, column (1-based), level (error or warning),
hook and message."""


def main(driver, args: list[str]) -> int:
    proc = subprocess.run(["getopt", "-u", "-o", "ehv", "-l", "error,json,stdin,help,version,plugins:",
                           "--", *words(" ".join(args))],
                          capture_output=True, text=True, env=driver.base_env())
    opts = words(proc.stdout)
    warnings = "--error" not in opts
    as_json = "--json" in opts
    stdin = "--stdin" in opts

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 1

    names = words(" ".join(driver.modules))
    if stdin and len(names) != 1:
        print("error: --stdin needs a single plug-in", file=sys.stderr)
        return 1
    status = 0
    found: list[dict] = []
    for name in names:
        path, reason = resolve(driver, name)
        if path is None and stdin and name.endswith(".yaml"):
            #  a new file, not saved yet
            path, reason = Path(name), ""
        if path is None:
            if as_json:
                found.append({"file": name, "line": 0, "column": 0, "level": ERROR, "hook": "",
                              "message": f"skipped: {reason}"})
            else:
                print()
                print(f"========== Skip {name}: {reason}")
            if reason != "not found":
                status = 1
            continue
        if warnings and not as_json:
            print()
            print(f"========== Handle {display(driver, path)}")
        plugin = path.name[: -len(".yaml")]
        text = sys.stdin.read() if stdin else path.read_text(errors="replace")
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
                status = 1
            elif not warnings:
                continue
            if as_json:
                found.append({"file": str(path), "line": issue.line, "column": issue.column,
                              "level": issue.level, "hook": issue.where, "message": issue.message})
            elif issue.level == ERROR:
                print(f"   error:   ({issue.where}) {issue.message}")
            else:
                print(f"   warning: ({issue.where}) {issue.message}")
    if as_json:
        print(json.dumps(found, indent=1))
    sys.stdout.flush()
    return status
