"""Construction of the plug-in model (scbi.plugin.model) from plain values,
independent of the file format.

A reader of a plug-in format (scbi.plugin.yamlfmt today) only deals with
its syntax: it finds the hooks, qualifiers, items and texts in the file,
then builds the model objects with these functions, which do the checks
common to every format (conditions, built-in functions, environment
actions, command bodies, records, qualifiers). They raise
:class:`DefinitionError` without location; the reader adds its own (file,
key, line).
"""

from __future__ import annotations

import re

from collections.abc import Callable, Iterable

from scbi.plugin import catalog
from scbi.plugin.expr import ExprError, parse
from scbi.plugin.model import (
    BUILTINS,
    ENV_VERBS,
    Commands,
    EnvOp,
    Function,
    Guarded,
    LocalAssign,
    Values,
    unknown_builtins,
)

#  NAME = <value>: a local variable of a value or environment list
_LOCAL = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s+=(?:\s+(.*)|\s*)$", re.S)

#  Fields of the record hooks, in order, and the count of mandatory ones
RECORDS = {
    "vcs": ("proxy", "options", "protocol", "url", "dir"),
    "archive": ("proxy", "options", "protocol", "url", "file", "dir"),
}
RECORD_MIN = {"vcs": 4, "archive": 5}

#  Qualifier names with a meaning in the model (not variant names)
COMMON = "common"
DEFAULT = "default"


class DefinitionError(Exception):
    """An invalid plug-in definition (message without location)."""


def guarded(cond: str, items: Iterable, convert: Callable) -> Guarded:
    """Items applied only when the condition ``cond`` is true."""
    try:
        parse(cond)
    except ExprError as e:
        raise DefinitionError(str(e)) from None
    return Guarded(cond, tuple(convert(i) for i in items))


def check_builtins(text: str) -> str:
    """A value or environment text: only the built-in functions in $(...)
    and supported expansions."""
    from scbi.hooks.expand import ExpandError, check

    bad = unknown_builtins(text)
    if bad:
        raise DefinitionError(f"unknown function $({bad[0]} ...) (allowed: {', '.join(BUILTINS)})")
    try:
        check(text)
    except ExpandError as e:
        raise DefinitionError(str(e)) from None
    return text


def local_assign(text: str) -> LocalAssign | None:
    """``NAME = <value>`` (None: not an assignment)."""
    m = _LOCAL.match(text)
    if not m:
        return None
    a = LocalAssign(m.group(1), (m.group(2) or "").strip())
    check_builtins(a.text)
    return a


def value(text: str) -> str | LocalAssign:
    """An item of a value hook."""
    return local_assign(text) or check_builtins(text)


def env_action(text: str) -> EnvOp | LocalAssign:
    """An environment action "<verb> <args>" or a local variable."""
    a = local_assign(text)
    if a:
        return a
    words = text.split(None, 1)
    verb = words[0] if words else ""
    if verb not in ENV_VERBS:
        raise DefinitionError(f"unknown environment action {verb!r}")
    rest = words[1] if len(words) > 1 else ""
    arity = ENV_VERBS[verb]
    if verb == "import":
        return EnvOp(verb, (rest,))
    check_builtins(rest)
    if arity == 0:
        if rest:
            raise DefinitionError(f"{verb} takes no argument")
        return EnvOp(verb, ())
    if arity < 0:
        return EnvOp(verb, tuple(rest.split()))
    parts = rest.split(None, arity - 1)
    if len(parts) != arity:
        raise DefinitionError(f"{verb} takes {arity} arguments")
    return EnvOp(verb, tuple(parts))


def _parsed(obj):
    from scbi.hooks.cmdlang import CmdSyntaxError

    try:
        obj.ast
    except CmdSyntaxError as e:
        raise DefinitionError(str(e)) from None
    return obj


def commands(text: str, line: int = 1) -> Commands:
    """A command hook body in the command language (``line``: its first
    line in the file), parsed now: a syntax error is a definition error."""
    return _parsed(Commands(text.rstrip("\n"), line))


def function(params: Iterable[str], text: str, line: int = 1) -> Function:
    """A plug-in function in the command language."""
    return _parsed(Function(tuple(params), text.rstrip("\n"), line))


def is_record(hook: str, fields) -> bool:
    """``fields`` (names) are those of the record hook ``hook``."""
    return hook in RECORDS and set(fields) <= set(RECORDS[hook])


def record(hook: str, fields: dict[str, str]) -> Values:
    """A record hook (vcs, archive) given by its fields."""
    names = RECORDS[hook]
    missing = [f for f in names[: RECORD_MIN[hook]] if f not in fields]
    if missing:
        raise DefinitionError(f"missing fields {missing}")
    return Values(tuple(str(fields[f]) for f in names if f in fields))


def check_qualifier(hook: str, qualifier: str) -> None:
    """``common`` only for the cumulative hooks."""
    if qualifier == COMMON and not catalog.spec(hook).cumulative:
        raise DefinitionError("'common' is only allowed for cumulative hooks")


def variant_members(members: Iterable[str]) -> tuple[str, ...]:
    """The variants a composite variant includes."""
    members = tuple(members)
    if not members or any(not m or "." in m for m in members):
        raise DefinitionError("a list of variant names is expected")
    return members
