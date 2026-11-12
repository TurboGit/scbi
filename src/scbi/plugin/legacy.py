"""Loader of the legacy plug-ins written in Bash.

A Bash plug-in is sourced in a Bash process where ``inherit-plugin`` and
``with-variant`` are replaced by shims recording the call. Before each such
call (and at the end) the functions defined so far are recorded, so that
the effect of the calls can be replayed in Python in the same order as Bash
would do (see scbi.plugin.registry): a function defined before an
``inherit-plugin`` call is kept, one defined after overrides the inherited
copy, ``with-variant`` always overrides...

The result is a :class:`PluginTrace`; nothing of the inheritance or native
variant semantics is implemented here.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from scbi.bashenv import BASH_INTERNAL


@dataclass
class Call:
    """A call to ``inherit-plugin`` or ``with-variant`` in a plug-in."""

    name: str
    args: list[str]
    #  Functions (name -> definition) defined by the plug-in before the call
    functions: dict[str, str]


@dataclass
class PluginTrace:
    name: str
    path: Path
    calls: list[Call] = field(default_factory=list)
    #  Functions defined at the end of the plug-in file
    functions: dict[str, str] = field(default_factory=dict)
    #  Global variables set by the plug-in (e.g. SCBI_LAL_LIBS=static)
    variables: dict[str, str] = field(default_factory=dict)
    #  Output of the plug-in file when sourced with the shims
    output: str = ""
    #  The file has top-level code besides functions, inherit-plugin /
    #  with-variant calls and assignments (it may print when sourced)
    has_code: bool = False


class LegacyLoadError(Exception):
    pass


_SHIM = r"""
shopt -s extglob
__scbi_snap()
{
    local f
    for f in $(compgen -A function); do
        [[ $f == __scbi_* ]] && continue
        [[ $f == inherit-plugin || $f == with-variant ]] && continue
        printf 'F\0%s\0%s\0' "$f" "$(declare -f "$f")"
    done
}
__scbi_call()
{
    __scbi_snap
    printf 'C\0%s\0%s\0' "$1" "$(( $# - 1 ))"
    shift
    local a
    for a in "$@"; do printf '%s\0' "$a"; done
}
inherit-plugin() { __scbi_call inherit-plugin "$@" >&3; }
with-variant()   { __scbi_call with-variant "$@" >&3; }
__scbi_vars_before=" $(compgen -v | tr '\n' ' ') "
"""

_END = r"""
__scbi_snap >&3
printf 'E\0' >&3
for __scbi_v in $(compgen -v); do
    [[ $__scbi_v == __scbi_* ]] && continue
    [[ $__scbi_vars_before == *" $__scbi_v "* ]] && continue
    __scbi_a=${!__scbi_v@a}
    [[ $__scbi_a == *[aA]* ]] && continue
    printf 'V\0%s\0%s\0' "$__scbi_v" "${!__scbi_v}" >&3
done
"""


def trace_plugin(path: Path, env: dict[str, str] | None = None) -> PluginTrace:
    """Source the Bash plug-in ``path`` and record what it defines."""
    path = Path(path)
    quoted = "'" + str(path).replace("'", "'\\''") + "'"
    script = f"{_SHIM}\nsource {quoted}\n{_END}\n"
    proc = subprocess.run(
        ["bash", "-c", 'exec 3>&1 1>&2; eval "$1"', "scbi-legacy", script],
        env=env if env is not None else {"PATH": "/usr/bin:/bin", "LANG": "C"},
        capture_output=True,
    )
    if proc.returncode != 0:
        raise LegacyLoadError(
            f"cannot load plug-in {path}: {proc.stderr.decode(errors='replace')}"
        )

    trace = PluginTrace(path.name, path, output=proc.stderr.decode(errors="replace"),
                        has_code=has_toplevel_code(path.read_text(errors="replace")))
    items = proc.stdout.decode(errors="surrogateescape").split("\0")
    snapshot: dict[str, str] = {}
    i = 0
    while i < len(items) and items[i] != "":
        kind = items[i]
        if kind == "F":
            snapshot[items[i + 1]] = items[i + 2]
            i += 3
        elif kind == "C":
            name, count = items[i + 1], int(items[i + 2])
            args = items[i + 3 : i + 3 + count]
            trace.calls.append(Call(name, args, snapshot))
            snapshot = {}
            i += 3 + count
        elif kind == "E":
            trace.functions = snapshot
            snapshot = {}
            i += 1
        elif kind == "V":
            if not BASH_INTERNAL.match(items[i + 1]):
                trace.variables[items[i + 1]] = items[i + 2]
            i += 3
        else:
            raise LegacyLoadError(f"unexpected trace record {kind!r} for {path}")
    return trace


_TOPLEVEL_OK = re.compile(
    r"^\s*($|#|function\s|[A-Za-z_][A-Za-z0-9_]*=|inherit-plugin\b|with-variant\b|export\s+-f\b)"
)


def has_toplevel_code(text: str) -> bool:
    """True when the plug-in has top-level code other than function
    definitions, inherit-plugin / with-variant calls and assignments."""
    in_function = False
    continuation = False
    for line in text.split("\n"):
        if in_function:
            if line.startswith("}"):
                in_function = False
            continue
        if continuation:
            continuation = line.rstrip().endswith("\\")
            continue
        if re.match(r"^\s*function\s", line) or re.match(r"^[A-Za-z0-9_.@+-]+\s*\(\)", line):
            in_function = not line.rstrip().endswith("}")
            continue
        if not _TOPLEVEL_OK.match(line):
            return True
        continuation = line.rstrip().endswith("\\")
    return False
