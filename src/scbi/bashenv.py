"""The driver variables (``ShellVars``), as the shell variables of the
Bash driver: scalar values, which are exported, arrays.

Also the quoting of a value for the Bash files the driver writes
(env.cmd...) and the names of the variables owned by Bash (used by the
migration loader of Bash plug-ins, scbi.plugin.legacy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#  Variables owned by Bash itself, never imported from a Bash plug-in
BASH_INTERNAL = re.compile(
    r"^(BASH.*|BASHOPTS|COLUMNS|COMP_.*|DIRSTACK|EUID|FUNCNAME|GROUPS|HISTCMD|"
    r"HOSTNAME|HOSTTYPE|IFS|LINENO|LINES|MACHTYPE|OPTERR|OPTIND|OSTYPE|PIPESTATUS|"
    r"PPID|PS4|PWD|OLDPWD|RANDOM|SECONDS|SHELLOPTS|SHLVL|SRANDOM|UID|_|EPOCH.*|"
    r"__scbi_.*)$"
)


@dataclass
class ShellVars:
    """Scalar variables (and which are exported) and arrays."""

    values: dict[str, str] = field(default_factory=dict)
    exported: set[str] = field(default_factory=set)
    #  Arrays: name -> (kind, content); kind "a" (indexed, keys are the
    #  indexes) or "A" (associative)
    arrays: dict[str, tuple[str, dict[str, str]]] = field(default_factory=dict)

    def copy(self) -> "ShellVars":
        return ShellVars(dict(self.values), set(self.exported),
                         {k: (kind, dict(c)) for k, (kind, c) in self.arrays.items()})

    def set(self, name: str, value: str, export: bool = False) -> None:
        self.values[name] = value
        if export:
            self.exported.add(name)

    def environ(self) -> dict[str, str]:
        """Exported variables, as seen by a child process."""
        return {k: v for k, v in self.values.items() if k in self.exported}


def quote(value: str) -> str:
    """The value as one Bash word (single quotes)."""
    return "'" + value.replace("'", "'\\''") + "'"
