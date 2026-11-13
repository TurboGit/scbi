"""Expansion of the values of plug-in definitions and environment action arguments.

A value is text where ``$NAME`` and ``${NAME}`` are replaced by the hook
parameter or shell variable ``NAME`` (empty when undefined) and
``$(function args...)`` by the output of a built-in function
(scbi.hooks.builtins). Inside ``$(...)`` the arguments are separated by
blanks, may be quoted, are expanded, and unquoted glob patterns are
expanded as in Bash before the call.

The output of a function has its trailing newlines removed and its lines
joined with a space (as an unquoted command substitution in an ``echo``).
Other shell syntax is rejected (see :func:`check`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase

from scbi.bashcompat import ShellSyntaxError, shell_words_glob
from scbi.hooks import builtins
from scbi.hooks.context import HookContext
from scbi.plugin.model import BUILTINS

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BRACED = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\[(?P<key>[^\]]+)\]|(?P<op>%%|%|##|#|:-)(?P<arg>[^{}$]*))?"
)


class ExpandError(Exception):
    pass


@dataclass(frozen=True)
class _Lit:
    text: str


@dataclass(frozen=True)
class _Var:
    name: str


@dataclass(frozen=True)
class _Op:
    """${NAME%pat} ${NAME%%pat} ${NAME#pat} ${NAME##pat} ${NAME:-default}
    ${NAME[key]}"""

    name: str
    op: str  # "%", "%%", "#", "##" or "[]"
    arg: str


@dataclass(frozen=True)
class _Cmd:
    name: str
    args: tuple  # ((segments, glob), ...)


def _parse(text: str) -> list:
    segs: list = []
    lit: list[str] = []
    i, n = 0, len(text)

    def flush() -> None:
        if lit:
            segs.append(_Lit("".join(lit)))
            lit.clear()

    while i < n:
        c = text[i]
        if c != "$":
            lit.append(c)
            i += 1
            continue
        nxt = text[i + 1 : i + 2]
        if nxt == "(":
            depth, j = 0, i + 1
            while j < n:
                if text[j] == "(":
                    depth += 1
                elif text[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= n:
                raise ExpandError(f"unterminated $( in {text!r}")
            inner = text[i + 2 : j]
            try:
                wds = shell_words_glob(inner)
            except ShellSyntaxError as e:
                raise ExpandError(str(e)) from None
            if not wds:
                raise ExpandError(f"empty $() in {text!r}")
            name = wds[0][0]
            if name not in BUILTINS:
                raise ExpandError(f"unknown function $({name} ...) in {text!r}")
            flush()
            segs.append(_Cmd(name, tuple((tuple(_parse(w)), g) for w, g in wds[1:])))
            i = j + 1
        elif nxt == "{":
            j = text.find("}", i)
            body = text[i + 2 : j] if j > 0 else ""
            m = _BRACED.fullmatch(body)
            if not m:
                raise ExpandError(f"unsupported expansion ${{{body}}} in {text!r}")
            flush()
            name, op, arg = m.group("name"), m.group("op"), m.group("arg")
            if m.group("key") is not None:
                segs.append(_Op(name, "[]", m.group("key")))
            elif op:
                segs.append(_Op(name, op, arg))
            else:
                segs.append(_Var(name))
            i = j + 1
        else:
            m = _NAME.match(text, i + 1)
            if m:
                flush()
                segs.append(_Var(m.group(0)))
                i = m.end()
            elif nxt and nxt in "?#@*!$-0123456789":
                raise ExpandError(f"unsupported special parameter ${nxt} in {text!r}")
            else:
                lit.append("$")
                i += 1
    flush()
    return segs


def _trim(value: str, op: str, pattern: str) -> str:
    """${VAR%pat} (shortest suffix), %% (longest), # and ## for prefixes,
    ${VAR:-default}."""
    if op == ":-":
        return value or pattern
    n = len(value)
    if op in ("%", "%%"):
        starts = range(n, -1, -1) if op == "%" else range(0, n + 1)
        for i in starts:
            if fnmatchcase(value[i:], pattern):
                return value[:i]
        return value
    ends = range(0, n + 1) if op == "#" else range(n, -1, -1)
    for i in ends:
        if fnmatchcase(value[:i], pattern):
            return value[i:]
    return value


def check(text: str) -> None:
    """Raise ExpandError if ``text`` uses unsupported syntax."""
    _parse(text)


def _eval(segs, ctx: HookContext) -> str:
    out = []
    for s in segs:
        if isinstance(s, _Lit):
            out.append(s.text)
        elif isinstance(s, _Var):
            out.append(ctx.lookup(s.name))
        elif isinstance(s, _Op):
            if s.op == "[]":
                out.append(ctx.arrays.get(s.name, {}).get(s.arg, ""))
            else:
                out.append(_trim(ctx.lookup(s.name), s.op, s.arg))
        else:
            args: list[str] = []
            for wsegs, glob in s.args:
                value = _eval(wsegs, ctx)
                args += builtins.bash_glob(value, ctx.cwd) if glob else [value]
            result = builtins.call(ctx, s.name, args).rstrip("\n")
            out.append(" ".join(result.split()))
    return "".join(out)


def expand(text: str, ctx: HookContext) -> str:
    try:
        return _eval(_parse(text), ctx)
    except builtins.BuiltinError as e:
        raise ExpandError(f"{e} in {text!r}") from None
