"""Expansion of the values of plug-in definitions and environment action arguments.

A value is text where ``$NAME`` and ``${NAME}`` are replaced by the hook
parameter or shell variable ``NAME`` (empty when undefined) and
``$(function args...)`` by the output of a built-in function
(scbi.hooks.builtins). Inside ``$(...)`` the arguments are separated by
blanks, may be quoted, are expanded, and unquoted glob patterns are
expanded as in Bash before the call.

The output of a function has its trailing newlines removed and its lines
joined with a space (as an unquoted command substitution in an ``echo``).

``$(if <condition> then A [else B])`` gives A when the condition (the
guard language, scbi.plugin.expr) is true, else B (empty when missing);
A and B are words expanded as the arguments of a function.

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
    r"(?:\[(?P<key>[^\]]+)\]|(?P<op>%%|%|##|#|:-|:\+|//|/)(?P<arg>[^{}]*))?"
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


@dataclass(frozen=True)
class _If:
    cond: str
    then: tuple  # ((segments, glob), ...)
    other: tuple


def _split_if(inner: str, text: str) -> tuple[str, str, str]:
    """``if COND then A [else B]``: the three texts. ``then`` and ``else``
    are words outside quotes and parentheses."""
    marks: list[tuple[str, int, int]] = []
    depth, quote, i, n = 0, "", 0, len(inner)
    while i < n:
        c = inner[i]
        if quote:
            if c == quote:
                quote = ""
            elif c == "\\" and quote == '"':
                i += 1
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and (i == 0 or inner[i - 1].isspace()):
            for kw in ("then", "else"):
                end = i + len(kw)
                if inner.startswith(kw, i) and (end == n or inner[end].isspace()):
                    marks.append((kw, i, end))
        i += 1
    kws = [m[0] for m in marks]
    if kws not in (["then"], ["then", "else"]):
        raise ExpandError(f"expected $(if <condition> then <value> [else <value>]) in {text!r}")
    cond = inner[len("if"):marks[0][1]].strip()
    then = inner[marks[0][2]:marks[1][1] if len(marks) > 1 else n]
    other = inner[marks[1][2]:] if len(marks) > 1 else ""
    if not cond:
        raise ExpandError(f"missing condition in {text!r}")
    return cond, then, other


def _words(text: str) -> tuple:
    try:
        wds = shell_words_glob(text)
    except ShellSyntaxError as e:
        raise ExpandError(str(e)) from None
    return tuple((tuple(_parse(w)), g) for w, g in wds)


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
            if inner.split(None, 1)[:1] == ["if"]:
                from scbi.plugin import expr

                cond, then, other = _split_if(inner, text)
                try:
                    expr.parse(cond)
                except expr.ExprError as e:
                    raise ExpandError(f"{e} in {text!r}") from None
                flush()
                segs.append(_If(cond, _words(then), _words(other)))
                i = j + 1
                continue
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
                #  the argument may refer to variables ($V): checked here,
                #  expanded when evaluated
                for part in (_split_replace(arg) if op in ("/", "//") else (arg,)):
                    _parse(part)
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


def _split_replace(arg: str) -> tuple[str, str]:
    """``pattern/replacement`` of ${VAR/...}: split at the first unescaped
    /, ``\\/`` giving a / (and \\x x in the replacement); ``\\$`` is kept,
    for _expand_arg (a literal $)."""
    i, pat = 0, []
    while i < len(arg) and arg[i] != "/":
        if arg[i] == "\\" and i + 1 < len(arg):
            pat.append(arg[i : i + 2] if arg[i + 1] == "$" else arg[i + 1])
            i += 2
            continue
        pat.append(arg[i])
        i += 1
    return "".join(pat), re.sub(r"\\([^$])", r"\1", arg[i + 1:])


def _expand_arg(text: str, ctx: HookContext) -> str:
    """The pattern or word of ${VAR<op>...} expanded, ``\\$`` giving a
    literal $ (as in Bash)."""
    if "$" not in text:
        return text
    return "$".join(_eval(_parse(piece), ctx) if "$" in piece else piece for piece in text.split("\\$"))


def _replace(value: str, arg: str, every: bool, pattern: str | None = None, repl: str = "") -> str:
    """${VAR/pattern/replacement} (first match, longest) and ${VAR//...}
    (every match); ``\\/`` is a / in the pattern. ``pattern`` and ``repl``
    given: already split (and expanded)."""
    if pattern is None:
        pattern, repl = _split_replace(arg)
    if not pattern:
        return value
    out, i, n = [], 0, len(value)
    while i < n:
        for j in range(n, i, -1):
            if fnmatchcase(value[i:j], pattern):
                out.append(repl)
                i = j
                if not every:
                    return "".join(out) + value[i:]
                break
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def _trim(value: str, op: str, pattern: str) -> str:
    """${VAR%pat} (shortest suffix), %% (longest), # and ## for prefixes,
    ${VAR:-default}."""
    if op == ":-":
        return value or pattern
    if op == ":+":
        return pattern if value else ""
    if op in ("/", "//"):
        return _replace(value, pattern, op == "//")
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
            elif s.op in ("/", "//"):
                pattern, repl = (_expand_arg(x, ctx) for x in _split_replace(s.arg))
                out.append(_replace(ctx.lookup(s.name), "", s.op == "//", pattern, repl))
            else:
                arg = _expand_arg(s.arg, ctx)
                out.append(_trim(ctx.lookup(s.name), s.op, arg))
        elif isinstance(s, _If):
            from scbi.hooks.evaluate import GuardContext
            from scbi.plugin import expr

            try:
                chosen = s.then if expr.evaluate(s.cond, GuardContext(ctx)) else s.other
            except expr.ExprError as e:
                raise builtins.BuiltinError(f"condition {s.cond!r}: {e}") from None
            values: list[str] = []
            for wsegs, glob in chosen:
                value = _eval(wsegs, ctx)
                values += builtins.bash_glob(value, ctx.cwd) if glob else [value]
            out.append(" ".join(values))
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
