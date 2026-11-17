"""Converter of Bash environment files (``.env``, ``.env-<name>``,
``.scbi-env-<name>``) to YAML environment files (scbi.envyaml).

    python3 -m scbi.envconvert [--check] FILE...

Converted:

- the settings ``NAME=value``, ``export NAME=value``,
  ``NAME=${NAME:-default}`` (``vars``: the same ``$X``, ``${X:-d}``...
  syntax); ``$(command args)`` becomes ``$(output command args)`` (a
  function of the values is kept as it is);
- the inclusion of another environment file, ``source
  ${SCBI_ENV_DIR}/.env-<x>`` (possibly guarded by ``[[ -f ... ]] &&``),
  becomes ``inherit: [<x>]``;
- the comments.

Anything else (functions such as ``module-final-step``,
``scbi-rewrite-vcs``, ``define-var``, commands, pipes in a value) is
reported: the file is not written and these parts are converted by hand
(the functions of scbi.envyaml). The output is ``FILE.yaml``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_ASSIGN = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_SOURCE = re.compile(r"^(?:\[\[\s+-f\s+(\S+)\s+\]\]\s+&&\s+)?(?:source|\.)\s+(\S+)$")
_ENV_NAME = re.compile(r"(?:^|/)\.(?:scbi-)?env-([\w.-]+?)(?:\.yaml)?$")


class Unconvertible(Exception):
    pass


def _value(text: str) -> str:
    """The value of a Bash assignment (right side of NAME=...), in the
    syntax of the values of the YAML files."""
    from scbi.plugin.model import BUILTINS

    if text.startswith("'") and text.endswith("'") and len(text) >= 2 and "'" not in text[1:-1]:
        if "$" in text:
            raise Unconvertible(f"literal $ not supported: {text}")
        return text[1:-1]
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1]
    elif any(c in re.sub(r"\$\([^()]*\)", "", text) for c in " \t;&<>`'\"\\"):
        raise Unconvertible(f"value not supported: {text}")
    if "`" in text:
        raise Unconvertible(f"command substitution not supported: {text}")

    def command(m: re.Match) -> str:
        inner = m.group(1).strip()
        if re.search(r"[|;&<>]", inner):
            raise Unconvertible(f"pipe or redirection in $( ) not supported: {text}")
        name = inner.split()[0] if inner.split() else ""
        return f"$({inner})" if name in BUILTINS else f"$(output {inner})"

    if "$(" in re.sub(r"\$\([^()]*\)", "", text):
        raise Unconvertible(f"nested $( ) not supported: {text}")
    return re.sub(r"\$\(([^()]*)\)", command, text)


def _scalar(value: str) -> str:
    """A YAML scalar (quoted when needed)."""
    if value == "" or re.search(r"""^[-?:,\[\]{}#&*!|>'"%@`\s]|[:#]\s|\s$|^(true|false|null|yes|no|on|off)$""",
                                value, re.I):
        return json.dumps(value)
    return value


def convert_text(text: str) -> tuple[str, list[str]]:
    """The YAML text of a Bash environment file and the lines which could
    not be converted."""
    head = ["#  Environment file (converted from Bash by scbi.envconvert)"]
    inherit: list[str] = []
    body: list[str] = []
    issues: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        #  [[ -f FILE ]] && \n source FILE
        while line.endswith("&&") and i < len(lines):
            line = line + " " + lines[i].strip()
            i += 1
        if not line:
            body.append("")
            continue
        if line.startswith("#"):
            body.append("  " + line)
            continue
        if re.match(r"^(function\s+)?[A-Za-z_][\w:.-]*\s*\(\)", line):
            #  a function: up to its closing brace at the start of a line
            start = i
            while i < len(lines) and lines[i].rstrip() != "}":
                i += 1
            i += 1
            issues.append(f"line {start}: function {line.split('(')[0].replace('function', '').strip()}: "
                          "convert it by hand (functions of scbi.envyaml)")
            continue
        m = _SOURCE.match(line)
        if m:
            name = _ENV_NAME.search(m.group(2))
            if name:
                inherit.append(name.group(1))
                continue
            issues.append(f"line {i}: source of a file which is not an environment file: {line}")
            continue
        m = _ASSIGN.match(line)
        if m:
            try:
                body.append(f"  {m.group(1)}: {_scalar(_value(m.group(2)))}")
            except Unconvertible as e:
                issues.append(f"line {i}: {e}")
            continue
        issues.append(f"line {i}: not supported: {line}")
    while body and body[-1] == "":
        body.pop()
    while body and body[0] == "":
        body.pop(0)
    out = head + [""]
    if inherit:
        out += ["inherit: [" + ", ".join(inherit) + "]", ""]
    if body:
        out += ["vars:"] + body
    return "\n".join(out).rstrip("\n") + "\n", issues


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
            out = path.with_name(path.name + ".yaml")
            out.write_text(text)
            print(f"{path}: written {out}")
    return status


if __name__ == "__main__":
    sys.exit(main())
