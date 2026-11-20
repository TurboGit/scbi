"""scbi schema: the JSON Schema of the YAML plug-ins (scbi.plugin.schema),
for the editors (completion, help on hover, structure checks)."""

from __future__ import annotations

import json
import sys

USAGE = """
SCBI-SCHEMA {version}

{argv0} schema [options]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions

Displays the JSON Schema (draft-07) of the YAML plug-ins: the hooks, their
qualifiers and the keys of the plug-in, with their description. The
content of the hooks is checked by scbi lint."""


def main(driver, args: list[str]) -> int:
    from scbi.plugin.schema import schema

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 1
    sys.stdout.write(json.dumps(schema(), indent=1) + "\n")
    sys.stdout.flush()
    return 0
