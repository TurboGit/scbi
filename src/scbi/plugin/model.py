"""Plug-in definition: the in-memory form of a plug-in recipe.

A :class:`PluginDef` is what a plug-in file declares, independently of its
format (legacy Bash lifted by scbi.plugin.lift, or a file read by the reader
of its format, scbi.plugin.formats). It is read-only input: the driver never writes it
back. The registry turns it into the namespace of hook functions used by
the resolution (scbi.plugin.resolve), applying inheritance and OS variants
in memory.

Hook bodies:

- :class:`Commands` command hooks (config, build...): a body in the
                   command language (scbi.hooks.cmdlang), parameters bound
                   by name from the catalog; custom functions
                   (:class:`Function`) use the same language.
- :class:`Values`  value hooks (depends, vcs, patches...): one item per
                   output line, possibly guarded by a condition.
- :class:`EnvOps`  env hooks: environment actions (add-to-var, set-var...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#  Qualifier of the plain hook (no variant): <plugin>-<hook>
PLAIN = ""


@dataclass(frozen=True)
class Guarded:
    """Items applied only when ``cond`` (scbi.plugin.expr syntax) is true."""

    cond: str
    items: tuple


@dataclass(frozen=True)
class Commands:
    """A body in the command language; ``line``: its first line in the
    plug-in file (for the messages, not compared)."""

    script: str
    line: int = field(default=1, compare=False)

    @property
    def ast(self) -> tuple:
        return _parse(self.script, self.line)

    def is_nop(self) -> bool:
        return self.script.strip() in ("", "true")


def _parse(script: str, line: int) -> tuple:
    from scbi.hooks.cmdlang import parse

    key = (script, line)
    if key not in _ASTS:
        _ASTS[key] = parse(script, line)
    return _ASTS[key]


_ASTS: dict[tuple[str, int], tuple] = {}


@dataclass(frozen=True)
class Values:
    #  str (a line, may use $VAR and built-in $(function ...)) or Guarded
    items: tuple


#  Command substitutions allowed in values and environment actions; they are
#  evaluated by the driver (no arbitrary shell outside command hooks)
BUILTINS = (
    "get-version",
    "get-build-type",
    "is-enabled",
    "last-modified-directory",
    "get-os-inc-dir",
    "basename",
    "ls",
)

_SUBST = re.compile(r"\$\(\s*([^\s)]*)")


def unknown_builtins(text: str) -> list[str]:
    """Names of the command substitutions of ``text`` not in BUILTINS."""
    return [n for n in _SUBST.findall(text) if n not in BUILTINS]


#  Environment actions: verb and arguments
ENV_VERBS = {
    "add-to-var": 2,
    "prepend-to-var": 2,
    "append-to-var": 2,
    "remove-from-var": 2,
    "set-var": 2,
    "define-var": 3,
    "unset-var": 1,
    "export": 2,  # export VAR=VALUE
    "local": 2,  # local VAR VALUE: variable for the following actions only
    "assign": 2,  # assign VAR VALUE: shell variable (VAR=VALUE), exported if it was
    "system-compiler": 0,
    "target-env": -1,  # optional arguments
    "no-target-env": -1,
    "mkdir": 1,
    "import": -1,  # import <command>: run and import printed variables
}


@dataclass(frozen=True)
class EnvOp:
    verb: str
    args: tuple[str, ...]


@dataclass(frozen=True)
class EnvOps:
    #  EnvOp or Guarded
    ops: tuple


@dataclass(frozen=True)
class Function:
    """Custom function callable from hooks (or used as a custom hook)."""

    params: tuple[str, ...]
    script: str
    line: int = field(default=1, compare=False)

    @property
    def ast(self) -> tuple:
        return _parse(self.script, self.line)


@dataclass(frozen=True)
class Inherit:
    parent: str
    hooks: tuple[str, ...] = ()
    custom_hooks: tuple[str, ...] = ()
    no_variant: bool = False
    name: str | None = None


@dataclass(frozen=True)
class WithVariant:
    """Variant using OS packages (legacy ``with-variant``)."""

    name: str
    packages: tuple[str, ...]
    env: tuple = ()  # EnvOp / Guarded


@dataclass(frozen=True)
class HookKey:
    hook: str  # catalog name, including pre-/post- steps
    qualifier: str = PLAIN  # PLAIN, "common", "default" or a variant name
    cross: bool = False

    def function_name(self, plugin: str) -> str:
        parts = [plugin]
        if self.qualifier:
            parts.append(self.qualifier)
        if self.cross:
            parts.append("cross")
        parts.append(self.hook)
        return "-".join(parts)


@dataclass
class PluginDef:
    name: str
    variables: dict[str, str] = field(default_factory=dict)
    inherits: list[Inherit] = field(default_factory=list)
    with_variants: list[WithVariant] = field(default_factory=list)
    #  Variants including other variants: {"all": ("ai", "hdr", "jxl")}.
    #  Only the hook lookup is affected (see scbi.plugin.resolve), the
    #  variant keeps its own name (sandbox, build id, logs, plans).
    variants: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #  name -> Function; names are full function names (may not start with
    #  the plug-in name)
    functions: dict[str, Function] = field(default_factory=dict)
    hooks: dict[HookKey, Commands | Values | EnvOps] = field(default_factory=dict)

    def function_names(self) -> set[str]:
        return {k.function_name(self.name) for k in self.hooks} | set(self.functions)
