"""Environment of a module build.

Port of the environment helpers of scripts.d/0_runtime: ``define-var``
(and ``add-to-var``, ``prepend-to-var``, ``append-to-var``,
``remove-from-var``, ``set-var``, ``unset-var``) and the list helpers they
use. The compiler environment of a build comes from the plug-ins (the
c-sandbox variants), not from the driver.

The Bash code splits and joins the values with unquoted expansions and
compares entries with glob patterns; this is reproduced so that the
resulting environment is identical (checked by tests/unit/test_env.py).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from scbi.bashcompat import words
from scbi.bashenv import ShellVars

ACTIONS = {
    "SET": "SET", "S": "SET",
    "UNSET": "UNSET", "U": "UNSET",
    "ADD": "ADD",
    "APPEND": "APPEND", "A": "APPEND",
    "PREPEND": "PREPEND", "P": "PREPEND",
    "REMOVE": "REMOVE", "R": "REMOVE",
}


def _match(value: str, pattern: str) -> bool:
    #  [[ $value == $pattern ]]: unquoted right side is a glob pattern
    return fnmatchcase(value, pattern)


# ---------------------------------------------------- list helpers (ports)


def _to_list(value: str, sep: str) -> list[str]:
    #  p_LIST=( ${_VAR//$SEP/ } )
    return words(value.replace(sep, " "))


def _to_var(items: list[str], sep: str) -> str:
    #  printf -v _VAR "%s$SEP" ${p_LIST[@]}; _VAR=${_VAR%?}
    flat = words(" ".join(items))
    return sep.join(flat) if flat else ""


def _first(value: str) -> str:
    #  the callers pass $VALUE unquoted, the function sees the first word
    w = words(value)
    return w[0] if w else ""


def _is_in_list(items: list[str], value: str) -> bool:
    #  [[ $VALUE = @(e1|e2|...) ]]
    flat = words(" ".join(items))
    if not flat:
        return value == ""
    return any(_match(value, e) for e in flat)


def _remove_from_list(items: list[str], value: str) -> list[str]:
    return [e for e in items if not _match(e, value)]


#  define_var(env, action, name, value): the define-var function of the
#  environment file (scbi.envyaml), set by the driver
USER_DEFINE_VAR: Callable | None = None

#  define-var of the Windows OS module (scripts.d/_os_windows) in effect:
#  ';' separator, PATH values converted with ``cygpath -u``
WINDOWS_DEFINE_VAR = False


def cygpath(path: str) -> str:
    """``$(cygpath -u PATH)``."""
    try:
        out = subprocess.run(["cygpath", "-u", path], capture_output=True, text=True).stdout
    except OSError:
        return ""
    return out.rstrip("\n")


class _UserEnv:
    """The ``env`` given to the user's ``define_var``."""

    def __init__(self, environment: "Environment"):
        self._e = environment

    def apply(self, action: str, name: str, value: str = "") -> None:
        """The default action (``define-var ACTION NAME VALUE``)."""
        self._e._define_var(action, name, value)

    def get(self, name: str) -> str:
        return self._e.get(name)


@dataclass
class Environment:
    """Shell variables of a module build (``ShellVars``) and the helpers."""

    vars: ShellVars = field(default_factory=ShellVars)
    #  SCBI_ENV_MODULE: file recording the define-var calls (env.cmd)
    record: Path | None = None
    #  in the user's define_var (env.apply calls the default action)
    _in_user: bool = field(default=False, repr=False, compare=False)
    windows: bool = False
    #  cygpath -u for Windows paths
    cygpath: Callable[[str], str] = lambda p: p

    def get(self, name: str) -> str:
        return self.vars.values.get(name, "")

    def export(self, name: str, value: str | None = None) -> None:
        if value is not None:
            self.vars.values[name] = value
        else:
            self.vars.values.setdefault(name, "")
        self.vars.exported.add(name)

    def unset(self, name: str) -> None:
        self.vars.values.pop(name, None)
        self.vars.exported.discard(name)

    def environ(self) -> dict[str, str]:
        return self.vars.environ()

    # ------------------------------------------------------------ define-var

    def define_var(self, action: str, var: str, value: str = "") -> None:
        """Port of ``define-var ACTION VAR VALUE``; with a ``define_var`` in
        the environment file (define-var), that function is called instead (it
        may apply the action with ``env.apply``)."""
        if USER_DEFINE_VAR is not None and not self._in_user:
            self._in_user = True
            try:
                USER_DEFINE_VAR(_UserEnv(self), action, var, value)
            finally:
                self._in_user = False
            return
        self._define_var(action, var, value)

    def _define_var(self, action: str, var: str, value: str = "") -> None:
        windows = self.windows or WINDOWS_DEFINE_VAR
        sep = ";" if windows else ":"

        #  If adding to PATH, do so only if VALUE exists
        if var == "PATH" and not os.path.isdir(value):
            return

        if self.record is not None:
            #  echo define-var $ACTION $VAR \"$VALUE\" >> $SCBI_ENV_MODULE
            line = " ".join(words(f'define-var {action} {var} "{value}"'))
            with open(self.record, "a") as f:
                f.write(line + "\n")

        if windows and var == "PATH":
            sep = ":"
            value = self.cygpath(value) if self.windows else cygpath(value)

        act = ACTIONS.get(action)
        current = self.get(var)

        if act == "SET":
            self.export(var, value)
        elif act == "UNSET":
            self.unset(var)
        #  The list helpers get $VALUE unquoted: only its first word is used
        elif act == "ADD":
            if value:
                items = _to_list(current, sep)
                if not _is_in_list(items, _first(value)):
                    items = words(_first(value)) + items
                self.export(var, _to_var(items, sep))
        elif act == "APPEND":
            if value:
                items = _remove_from_list(_to_list(current, sep), _first(value))
                self.export(var, _to_var(items + words(_first(value)), sep))
        elif act == "PREPEND":
            if value:
                items = _remove_from_list(_to_list(current, sep), _first(value))
                self.export(var, _to_var(words(_first(value)) + items, sep))
        elif act == "REMOVE":
            items = _remove_from_list(_to_list(current, sep), _first(value))
            self.export(var, _to_var(items, sep))
            if not self.get(var):
                self.unset(var)

    def add_to_var(self, var: str, value: str) -> None:
        self.define_var("ADD", var, value)

    def prepend_to_var(self, var: str, value: str) -> None:
        self.define_var("PREPEND", var, value)

    def append_to_var(self, var: str, value: str) -> None:
        self.define_var("APPEND", var, value)

    def remove_from_var(self, var: str, value: str) -> None:
        self.define_var("REMOVE", var, value)

    def set_var(self, var: str, value: str) -> None:
        self.define_var("SET", var, value)

    def unset_var(self, var: str) -> None:
        self.define_var("UNSET", var, "")
