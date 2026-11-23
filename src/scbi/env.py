"""Environment of a module build.

Port of the environment helpers of scripts.d/0_runtime: ``define-var``
(and ``add-to-var``, ``prepend-to-var``, ``append-to-var``,
``remove-from-var``, ``set-var``, ``unset-var``), the list helpers they use,
``system-compiler``, ``target-env`` (the environment of the sandbox) and
``set-compiler-paths``.

The Bash code splits and joins the values with unquoted expansions and
compares entries with glob patterns; this is reproduced so that the
resulting environment is identical (checked by tests/unit/test_env.py).
"""

from __future__ import annotations

import os
import shutil
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

    # ------------------------------------------------------- compiler setup

    def system_compiler(self) -> None:
        """Port of ``system-compiler``."""
        self.export("PATH", "/usr/local/bin:/usr/bin:/bin")
        for v in ("C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH",
                  "LD_LIBRARY_PATH", "ADA_PROJECT_PATH"):
            self.unset(v)

    def _gcc_prefix(self) -> str:
        gcc = shutil.which("gcc", path=self.get("PATH")) or ""
        return os.path.dirname(os.path.dirname(gcc)) if gcc else "."

    def _gcc_version(self) -> str:
        if self.windows:
            return "1"
        try:
            return subprocess.run(
                ["gcc", "-dumpversion"], capture_output=True, text=True, env=self.environ()
            ).stdout.strip()
        except OSError:
            return ""

    def set_compiler_paths(self, prefix: str, target: str, host: str, bdir: str) -> None:
        """Port of ``set-compiler-paths``."""
        ver = self._gcc_version()
        if not target:
            i1, i2 = f"{prefix}/include/{host}", f"{prefix}/include"
            i3, i4 = f"{prefix}/lib/gcc/{host}/{ver}/include", f"{prefix}/local/include"
            ip1, ip2 = f"{prefix}/include/c++/{ver}", ""
            p = f"{prefix}/{host}/share/gpr:{prefix}/share/gpr"
            lib = f"{prefix}/lib/{host}:{prefix}/lib"
        else:
            i1, i2 = f"{prefix}/lib/gcc/{target}/{ver}/include", f"{prefix}/include/{target}"
            i3, i4 = f"{prefix}/include", f"{prefix}/local/include"
            ip1, ip2 = f"{prefix}/include/{target}/c++/{ver}", f"{prefix}/include/c++/{ver}"
            p = f"{prefix}/{target}/share/gpr"
            lib = f"{prefix}/lib/{target}"
            ic = f"{bdir}/c-libiconv/x86_64-linux-gnu-default/install/lib"
            if os.path.isdir(ic):
                lib = f"{lib}:{ic}"
        self.export("C_INCLUDE_PATH", f"{i1}:{i2}:{i3}:{i4}")
        self.export("CPLUS_INCLUDE_PATH", f"{ip1}:{ip2}:{i1}:{i2}:{i3}:{i4}")
        self.export("LIBRARY_PATH", f"{lib}:/usr/lib")
        self.export("LD_LIBRARY_PATH", f"{lib}:/usr/lib")
        self.export("ADA_PROJECT_PATH", p)

    def target_env(self, prefix: str, target: str, host: str, bdir: str) -> None:
        """Port of ``target-env [PREFIX [TARGET]]``."""
        if not prefix:
            prefix = self._gcc_prefix()
        b = f"{prefix}/bin" if not target else f"{prefix}/{target}/bin"
        self.export("PATH", f"{b}:{self.get('PATH')}")
        self.set_compiler_paths(prefix, target, host, bdir)
