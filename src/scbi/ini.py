"""Ini files (``$HOME/.scbi``, ``./.scbi``, ``$SCBI_INI_FILE``).

Port of ``ini-load-file``, ``ini-load-files`` and ``ini-get-option`` from the
scbi driver. The database maps ``[section.]key`` to the raw value; values
are expanded as ``eval echo`` does in Bash (:func:`expand_value`, no
shell) when read.

``ini-apply-values`` (which sets the driver options) is part of the CLI.
"""

from __future__ import annotations

import glob as _glob
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from scbi.bashcompat import read_lines
from scbi.bashenv import ShellVars

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
        #  the sections, in order, and the (last) file defining each one
        self.sections: dict[str, Path] = {}

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
                self.sections.pop(section, None)
                self.sections[section] = Path(path)
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
        return expand_value(raw, svars.values.get)


_GLOB = re.compile(r"[*?\[]")


class _VarContext:
    """What scbi.hooks.expand needs to expand variables."""

    def __init__(self, getvar: Callable[[str], str | None], cwd: str):
        self.getvar = getvar
        self.arrays: dict = {}
        self.cwd = cwd

    def lookup(self, name: str) -> str:
        return self.getvar(name) or ""


def _command_output(text: str, getvar, cwd: str) -> str:
    """``$(command args...)``: the command run without a shell (its words
    expanded as an ini value)."""
    argv = _fields(text, getvar, cwd)
    if not argv:
        return ""
    env = {k: v for k, v in os.environ.items()}
    try:
        return subprocess.run(argv, capture_output=True, text=True, cwd=cwd, env=env).stdout
    except OSError:
        return ""


def _expand_text(text: str, getvar, cwd: str) -> str:
    """Variables and command substitutions of ``text``."""
    from scbi.hooks.expand import ExpandError, _eval, _parse

    out, i = [], 0
    while True:
        j = text.find("$(", i)
        if j < 0:
            break
        depth, k = 0, j + 1
        while k < len(text):
            depth += text[k] == "("
            depth -= text[k] == ")"
            if depth == 0:
                break
            k += 1
        out.append(_expand_text(text[i:j], getvar, cwd))
        out.append(_command_output(text[j + 2:k], getvar, cwd).rstrip("\n"))
        i = k + 1
    try:
        out.append(_eval(_parse(text[i:]), _VarContext(getvar, cwd)))
    except ExpandError:
        out.append(text[i:])
    return "".join(out)


def _fields(value: str, getvar, cwd: str) -> list[str]:
    """The words of ``value`` after expansion, field splitting of unquoted
    expansions, tilde and pathname expansion (as ``eval echo``)."""
    from scbi.hooks.cmdlang import CmdSyntaxError, Word, tokenize

    try:
        tokens = tokenize(value)
    except CmdSyntaxError:
        return value.split()
    fields: list[str] = []
    for tok in tokens:
        if not isinstance(tok, Word):
            fields.append(tok)
            continue
        cur, has, pattern, globbing = [], False, [], False
        word_fields: list[tuple[str, str, bool]] = []

        def end() -> None:
            nonlocal cur, has, pattern, globbing
            if "".join(cur) or has:
                word_fields.append(("".join(cur), "".join(pattern), globbing))
            cur, has, pattern, globbing = [], False, [], False

        for k, (part, quote) in enumerate(tok.parts):
            if quote == "'":
                cur.append(part)
                pattern.append(_glob.escape(part))
                has = True
                continue
            if quote == "" and k == 0 and (part == "~" or part.startswith("~/")):
                part = (getvar("HOME") or "") + part[1:]
            text = _expand_text(part, getvar, cwd)
            if quote == '"':
                cur.append(text)
                pattern.append(_glob.escape(text))
                has = True
                continue
            for n, piece in enumerate(re.split(r"[ \t\n]+", text)):
                if n > 0:
                    end()
                cur.append(piece)
                pattern.append(piece)
                globbing = globbing or bool(_GLOB.search(piece))
        end()
        for text, pat, globbing in word_fields:
            matches = sorted(_glob.glob(pat, root_dir=cwd)) if globbing else []
            fields += matches or [text]
    return fields


def expand_value(value: str, getvar: Callable[[str], str | None], cwd: str | None = None) -> str:
    """Result of ``eval echo <value>`` in Bash: quotes removed, variables
    (``$V``, ``${V}``, ``${V:-d}``, ``${V%p}``...), ``~``, ``$(command)``
    and globs expanded, the words joined with a space."""
    return " ".join(_fields(value, getvar, cwd or os.getcwd()))
