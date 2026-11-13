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
}
