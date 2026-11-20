"""scbi ini: the sections of the ini files (``$HOME/.scbi``,
``./.scbi``, ``$SCBI_INI_FILE``), each one started with
``scbi --ini=<section>``: for the editors (a task per section)."""

from __future__ import annotations

import json
import subprocess
import sys

from scbi.bashcompat import words

USAGE = """
SCBI-INI {version}

{argv0} ini [options]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --json             the sections as JSON (for the editors)

Lists the sections of the ini files (not common nor scbi-<sub-command>,
always used): the ones started with scbi --ini=<section>, with their file
and their modules, run and tests keys (as written).

With --json the output is a JSON list of objects with the keys name,
file, modules, run and tests."""

KEYS = ("modules", "run", "tests")


def sections(ini) -> list[dict]:
    """The sections of the ini database ``ini`` (scbi.ini.IniDB)."""
    result = []
    for name, path in ini.sections.items():
        if name == "common" or name.startswith("scbi-"):
            continue
        entry = {"name": name, "file": str(path.resolve())}
        for key in KEYS:
            value = ini.db.get(f"{name}.{key}", "")
            #  modules: accumulated over the files (words); run: a command
            entry[key] = " ".join(value.split()) if key == "modules" else value.strip()
        result.append(entry)
    return result


def main(driver, args: list[str]) -> int:
    proc = subprocess.run(["getopt", "-u", "-o", "hv", "-l", "json,help,version",
                           "--", *words(" ".join(args))],
                          capture_output=True, text=True, env=driver.base_env())
    as_json = "--json" in words(proc.stdout)
    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 1
    found = sections(driver.ini)
    if as_json:
        sys.stdout.write(json.dumps(found, indent=1) + "\n")
    else:
        for s in found:
            what = f"run: {s['run']}" if s["run"] else f"modules: {s['modules']}"
            print(f"{s['name']:20} {what}")
    sys.stdout.flush()
    return 0
