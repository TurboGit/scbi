"""Converter of Bash environment files (``.env``, ``.env-<name>``,
``.scbi-env-<name>``) to Python environment files (scbi.envpy).

    python3 -m scbi.envconvert [--check] FILE...

The settings are converted: ``NAME=value``, ``export NAME=value``,
``NAME=${NAME:-default}`` and references to other variables in values
(``$X``, ``${X}``, ``${X:-d}``) become calls of ``getvar``. Comments are
kept. Anything else (functions such as ``module-final-step``,
``scbi-rewrite-vcs``, ``define-var``, commands) is reported: the file is
not written and these parts are converted by hand (see the hooks of
scbi.envpy). The output is ``FILE.py``.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path

_ASSIGN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}|([A-Za-z_][A-Za-z0-9_]*))")


class Unconvertible(Exception):
    pass


def _value(text: str) -> str:
    """Python expression of a Bash value (the right side of NAME=...)."""
    if text.startswith("'") and text.endswith("'") and len(text) >= 2 and "'" not in text[1:-1]:
        return repr(text[1:-1])
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1]
    elif any(c in text for c in " \t;|&<>()`'\"\\"):
        raise Unconvertible(f"value not supported: {text}")
    if "$(" in text or "`" in text:
        raise Unconvertible(f"command substitution not supported: {text}")
    rest = _REF.sub("", text)
    if "$" in rest or any("$" in (m.group(2) or "") or "{" in (m.group(2) or "") for m in _REF.finditer(text)):
        raise Unconvertible(f"expansion not supported: {text}")
    parts: list[str] = []
    pos = 0
    for m in _REF.finditer(text):
        if m.start() > pos:
            parts.append(repr(text[pos:m.start()]))
        name = m.group(1) or m.group(3)
        default = m.group(2)
        parts.append(f"getvar({name!r}, {_value(default)})" if default else f"getvar({name!r})")
        pos = m.end()
    if pos < len(text) or not parts:
        parts.append(repr(text[pos:]))
    return " + ".join(parts)


def convert_text(text: str) -> tuple[str, list[str]]:
    """The Python text of a Bash environment file and the lines which could
    not be converted."""
    out = ['"""Environment file (converted from Bash by scbi.envconvert)."""', ""]
    issues: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            out.append("")
            continue
        if line.startswith("#"):
            out.append(line)
            continue
        if re.match(r"^(function\s+)?[A-Za-z_][\w:.-]*\s*\(\)", line):
            #  a function: up to its closing brace at the start of a line
            start = i
            while i < len(lines) and lines[i].rstrip() != "}":
                i += 1
            i += 1
            issues.append(f"line {start}: function {line.split('(')[0].replace('function', '').strip()}: "
                          "convert it by hand (hooks of scbi.envpy)")
            continue
        m = _ASSIGN.match(line)
        if m:
            try:
                out.append(f"{m.group(1)} = {_value(m.group(2))}")
            except Unconvertible as e:
                issues.append(f"line {i}: {e}")
            continue
        try:
            words = shlex.split(line)
        except ValueError:
            words = []
        issues.append(f"line {i}: not supported: {line}" if words else f"line {i}: syntax: {line}")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n", issues


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m scbi.envconvert", description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="only report, write nothing")
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args(argv)
    status = 0
    for path in args.files:
        text, issues = convert_text(path.read_text())
        if issues:
            status = 1
            for issue in issues:
                print(f"{path}: {issue}")
            continue
        if not args.check:
            out = path.with_name(path.name + ".py")
            out.write_text(text)
            print(f"{path}: written {out}")
    return status


if __name__ == "__main__":
    sys.exit(main())
