"""Positions in the file of the issues of the linter (scbi.plugin.lint),
for the editors: the line and column (1-based) of what an issue is
about.

An issue names its place with ``where``: a hook and its qualifiers
(``config``, ``config.cross._``, ``config-options.vara``), ``function
<name>``, ``plugin``, or a path of keys of a loader error
(``functions.f.run``). The position is the one of the key; refined, in
the body of the hook, to the line given by the message (``line N: ...``
of a command body) or to the variable the message is about.
"""

from __future__ import annotations

import re
from dataclasses import replace

import yaml

from scbi.plugin import yamlfmt

#  the variable a message is about
_VAR_MESSAGES = (
    re.compile(r"^variable (\w+) is not known"),
    re.compile(r"^(\w+) is a parameter of "),
)
_UNUSED = re.compile(r"^line \d+: variable (\w+) is set but never used")
_LINE = re.compile(r"^line (\d+): ")


def _resolve(root, where: str):
    """(key node, value node) of ``where`` in the mapping ``root`` (keys
    may contain dots: the longest key first), the deepest found."""
    found = (None, None)
    node, rest = root, where
    while rest and isinstance(node, yaml.MappingNode):
        best = None
        for k, v in node.value:
            key = str(k.value)
            if (rest == key or rest.startswith(key + ".")) and (best is None or len(key) > len(str(best[0].value))):
                best = (k, v)
        if best is None:
            break
        found = best
        node = best[1]
        rest = rest[len(str(best[0].value)) + 1:]
    return found


def _place(root, where: str):
    if where.startswith("function "):
        name = where[len("function "):]
        k, v = _resolve(root, f"functions.{name}.run")
        if k is None or str(k.value) != "run":
            k, v = _resolve(root, f"functions.{name}")
        return k, v
    return _resolve(root, where)


def _search(lines: list[str], start: int, end: int, pattern: re.Pattern):
    """(line, column) 1-based of the first match in lines[start:end+1]."""
    for n in range(max(start, 0), min(end, len(lines) - 1) + 1):
        m = pattern.search(lines[n])
        if m:
            return n + 1, m.start() + 1
    return None


def locate(text: str, issues: list) -> list:
    """The issues with their position (line and column) in ``text``;
    unchanged when the text cannot be read (a YAML error has its own)."""
    try:
        root = yaml.compose(text, Loader=yamlfmt._Loader)
    except yaml.YAMLError:
        return issues
    lines = text.splitlines()
    result = []
    for issue in issues:
        if issue.line:
            result.append(issue)
            continue
        key, value = _place(root, issue.where) if root is not None else (None, None)
        if key is None:
            result.append(replace(issue, line=1, column=1))
            continue
        line, column = key.start_mark.line + 1, key.start_mark.column + 1
        first = value.start_mark.line
        last = value.end_mark.line
        m = _LINE.match(issue.message)
        if m and isinstance(value, yaml.ScalarNode):
            #  the line of a command body
            start = value.start_mark.line + (1 if value.style in ("|", ">") else 0)
            n = start + int(m.group(1)) - 1
            if n < len(lines):
                line = n + 1
                column = len(lines[n]) - len(lines[n].lstrip()) + 1
                first = last = n
        var = None
        for pattern in _VAR_MESSAGES:
            mv = pattern.match(issue.message)
            if mv:
                var = re.compile(rf"\$\{{?[#!]?{mv.group(1)}\b")
        mu = _UNUSED.match(issue.message)
        if mu:
            var = re.compile(rf"\b{mu.group(1)}\s*=")
        if var is not None:
            pos = _search(lines, first, last, var)
            if pos is not None:
                line, column = pos
        result.append(replace(issue, line=line, column=column))
    return result
