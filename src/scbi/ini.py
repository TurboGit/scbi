"""Ini files (``$HOME/.scbi``, ``./.scbi``, ``$SCBI_INI_FILE``).

Port of ``ini-load-file``, ``ini-load-files`` and ``ini-get-option`` from the
scbi driver. The database maps ``[section.]key`` to the raw value; values
are expanded by the shell (``eval echo``) when read.

``ini-apply-values`` (which sets the driver options) is part of the CLI.
"""

from __future__ import annotations

import re
from pathlib import Path

from scbi.bashcompat import read_lines
from scbi.bashenv import ShellVars, eval_echo

#  Keys whose values are accumulated (space separated) instead of replaced
MULTI_KEYS = ("enable", "modules", "options")

#  Note: "[:space:]" outside brackets is, as in the Bash code, a bracket
#  expression matching the characters ":", "s", "p", "a", "c" and "e".
_COMMENT = re.compile(r"^[:space:]*#(.*)")
_SECTION = re.compile(r"^(\[)(.*)(\])$")
_KEYVAL = re.compile(r"^([^=]+)=([^=]+)$")


class IniDB:
    def __init__(self) -> None:
        self.db: dict[str, str] = {}

    def load_file(self, path: Path) -> None:
        """Port of ``ini-load-file``."""
        section = ""
        for raw in read_lines(Path(path).read_text()):
            #  read -r line: IFS whitespace removed at both ends
            line = raw.strip(" \t\n")
            if _COMMENT.match(line):
                continue
            m = _SECTION.match(line)
            if m:
                section = m.group(2)
                continue
            m = _KEYVAL.match(line)
            if not m:
                continue
            key = m.group(1).replace(" ", "")
            val = m.group(2)
            #  ${BASH_REMATCH[2]%%+ }: literal "+ " suffix
            if val.endswith("+ "):
                val = val[:-2]
            if not key:
                continue
            db_key = f"{section}.{key}" if section else key
            if key in MULTI_KEYS:
                self.db[db_key] = self.db.get(db_key, "") + f"{val} "
            else:
                self.db[db_key] = val

    def load_files(self, home: Path, cwd: Path, ini_file: str | None) -> None:
        """Port of ``ini-load-files``."""
        for path in (Path(home) / ".scbi", Path(cwd) / ".scbi"):
            if path.is_file():
                self.load_file(path)
        if ini_file and Path(ini_file).is_file():
            self.load_file(Path(ini_file))

    def raw_option(self, section: str, var: str) -> str | None:
        """Raw value selected by ``ini-get-option`` (before expansion)."""
        if self.db.get(f"{section}.{var}"):
            return self.db[f"{section}.{var}"]
        if section and self.db.get(f"common.{var}"):
            return self.db[f"common.{var}"]
        if self.db.get(var):
            return self.db[var]
        return None

    def get_option(self, section: str, var: str, svars: ShellVars, base_env=None) -> str:
        """Port of ``ini-get-option``: value expanded with ``eval echo``."""
        raw = self.raw_option(section, var)
        if raw is None:
            return ""
        return eval_echo(raw, svars, base_env)
