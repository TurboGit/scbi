"""scbi format: write YAML plug-ins in the canonical form
(scbi.plugin.yamlwrite): canonical order of the keys, block style,
comments kept.

Bash plug-ins are not formatted: they are converted to YAML once with
``python3 -m scbi.convert`` (whose output is canonical).
"""

from __future__ import annotations

import subprocess
import sys

from scbi.bashcompat import words
from scbi.plugin.yamlfmt import FormatError
from scbi.plugin.yamlwrite import WriteError, format_text
from scbi.tools.plugins import resolve

USAGE = """
SCBI-FORMAT {version}

{argv0} format [options] plug-in1 [plug-in2...]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --plugins=<dir>    specify the plugins' directory
      | --replace          replace the plug-in by its formatted version
      | --stdin            the text of the (single) plug-in from the
                           standard input, the formatted text written to
                           the standard output (e.g. an unsaved buffer)
      | --stat             display some status of current setup

Formats YAML plug-ins (<name>.yaml) in the canonical form."""


def main(driver, args: list[str]) -> int:
    proc = subprocess.run(["getopt", "-u", "-o", "ehv", "-l", "replace,stdin,help,version,plugins:",
                           "--", *words(" ".join(args))],
                          capture_output=True, text=True, env=driver.base_env())
    replace = "--replace" in words(proc.stdout)
    stdin = "--stdin" in words(proc.stdout)

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 1

    if stdin:
        #  the name gives the plug-in name only (the file may not exist)
        names = words(" ".join(driver.modules))
        if len(names) != 1:
            print("error: --stdin needs a single plug-in", file=sys.stderr)
            return 1
        base = names[0].rsplit("/", 1)[-1]
        try:
            text = format_text(base[: -len(".yaml")] if base.endswith(".yaml") else base, sys.stdin.read())
        except (FormatError, WriteError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        sys.stdout.write(text)
        sys.stdout.flush()
        return 0

    status = 0
    for name in words(" ".join(driver.modules)):
        path, reason = resolve(driver, name)
        if path is None:
            print()
            print(f"========== Skip {name}: {reason}")
            if reason != "not found":
                status = 1
            continue
        plugin = path.name[: -len(".yaml")]
        try:
            text = format_text(plugin, path.read_text())
        except (FormatError, WriteError) as e:
            print(f"error: {e}")
            status = 1
            continue
        if replace:
            print(f"========== Reformat {name}")
            if text != path.read_text():
                path.write_text(text)
        else:
            sys.stdout.write(text)
    sys.stdout.flush()
    return status
