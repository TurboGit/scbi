"""Sub-commands of the driver ported to Python (scbi <sub-command>).

A sub-command without a Python implementation here runs the reference
Bash script scbi-<sub-command> (see Driver.run_tool); so does a Python
implementation returning None (options not ported yet).
"""

from __future__ import annotations

TOOLS = {
    "store": "scbi.tools.store",
    "show": "scbi.tools.show",
    "shell": "scbi.tools.shell",
    "source-archive": "scbi.tools.source_archive",
    "lint": "scbi.tools.lint",
    "format": "scbi.tools.format",
    "replay": "scbi.tools.replay",
    "schema": "scbi.tools.schema",
    "ini": "scbi.tools.ini",
}

#  sub-commands without a Bash script (scbi-<sub-command>)
PYTHON_ONLY = ("replay", "schema", "ini")
