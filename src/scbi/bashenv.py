"""Evaluate Bash configuration files and import the resulting variables.

Some SCBI inputs are Bash code meant to be sourced by the driver:
environment files (``.scbi-env*``, ``$SCBI_PLUGINS/.env*``), setup runtime
files that a user or the testsuite may override (``$SCBI_PLUGINS/1_setup``)
and ini values (``eval echo``). The Python driver evaluates them in a Bash
process seeded with its own variables and imports the scalar variables
back.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from scbi.bashcompat import words

#  Variables owned by Bash itself, never imported
BASH_INTERNAL = re.compile(
    r"^(BASH.*|BASHOPTS|COLUMNS|COMP_.*|DIRSTACK|EUID|FUNCNAME|GROUPS|HISTCMD|"
    r"HOSTNAME|HOSTTYPE|IFS|LINENO|LINES|MACHTYPE|OPTERR|OPTIND|OSTYPE|PIPESTATUS|"
    r"PPID|PS4|PWD|OLDPWD|RANDOM|SECONDS|SHELL|SHELLOPTS|SHLVL|SRANDOM|UID|_|EPOCH.*|"
    r"__scbi_.*)$"
)

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#  Arrays owned by Bash itself, never imported
_BASH_ARRAYS = re.compile(r"^(BASH_.*|DIRSTACK|FUNCNAME|GROUPS|PIPESTATUS|COMP_.*|__scbi_.*)$")


class BashEvalError(RuntimeError):
    def __init__(self, message: str, returncode: int, output: str):
        super().__init__(message)
        self.returncode = returncode
        self.output = output


@dataclass
class ShellVars:
    """Scalar shell variables (and which are exported) and Bash functions.

    ``functions`` maps a function name to its full definition (as printed
    by ``declare -f``); these are user code defined in sourced files (e.g.
    ``module-final-step`` or ``scbi-rewrite-vcs`` in an environment file)
    that must be made available where the driver calls them.
    """

    values: dict[str, str] = field(default_factory=dict)
    exported: set[str] = field(default_factory=set)
    functions: dict[str, str] = field(default_factory=dict)
    #  Arrays: name -> (kind, content); kind "a" (indexed, keys are the
    #  indexes) or "A" (associative)
    arrays: dict[str, tuple[str, dict[str, str]]] = field(default_factory=dict)

    def copy(self) -> "ShellVars":
        return ShellVars(dict(self.values), set(self.exported), dict(self.functions),
                         {k: (kind, dict(c)) for k, (kind, c) in self.arrays.items()})

    def set(self, name: str, value: str, export: bool = False) -> None:
        self.values[name] = value
        if export:
            self.exported.add(name)

    def environ(self) -> dict[str, str]:
        """Exported variables, as seen by a child process."""
        return {k: v for k, v in self.values.items() if k in self.exported}


def quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def seed(svars: ShellVars) -> str:
    lines = []
    for name, value in svars.values.items():
        if not _NAME.match(name) or BASH_INTERNAL.match(name):
            continue
        prefix = "export " if name in svars.exported else ""
        lines.append(f"{prefix}{name}={quote(value)}")
    for name, (kind, content) in svars.arrays.items():
        if not _NAME.match(name) or _BASH_ARRAYS.match(name):
            continue
        items = " ".join(f"[{quote(k)}]={quote(v)}" for k, v in content.items())
        lines.append(f"declare -g{'A' if kind == 'A' else 'a'} {name}=({items})")
    lines += svars.functions.values()
    return "\n".join(lines)


_DUMP = r"""
for __scbi_v in $(compgen -v); do
    [[ $__scbi_v == __scbi_* ]] && continue
    __scbi_a=${!__scbi_v@a}
    if [[ $__scbi_a == *[aA]* ]]; then
        [[ $__scbi_a == *A* ]] && __scbi_k=A || __scbi_k=a
        declare -n __scbi_r=$__scbi_v
        for __scbi_i in "${!__scbi_r[@]}"; do
            printf 'R\0%s\0%s\0%s\0' "$__scbi_v" "$__scbi_k:$__scbi_i" "${__scbi_r[$__scbi_i]}"
        done
        printf 'R\0%s\0%s\0\0' "$__scbi_v" "$__scbi_k"
        unset -n __scbi_r
        continue
    fi
    __scbi_x=0
    [[ $__scbi_a == *x* ]] && __scbi_x=1
    printf 'V\0%s\0%s\0%s\0' "$__scbi_v" "$__scbi_x" "${!__scbi_v}"
done
for __scbi_f in $(compgen -A function); do
    [[ " $__scbi_known " == *" $__scbi_f "* ]] && continue
    printf 'F\0%s\0%s\0%s\0' "$__scbi_f" "" "$(declare -f $__scbi_f)"
done
"""


def source_files(
    files: Iterable[Path | str],
    svars: ShellVars,
    cwd: Path | None = None,
    base_env: Mapping[str, str] | None = None,
    prelude: str = "",
) -> ShellVars:
    """Source ``files`` in order in Bash seeded with ``svars``.

    Returns all scalar variables afterwards (Bash internal ones excluded).
    A file calling ``exit`` (with a non-zero status) raises BashEvalError.
    ``base_env`` is the process environment of the Bash process (PATH,
    HOME...), exported variables of ``svars`` are added to it.
    """
    script = [
        "shopt -s extglob",
        prelude,
        #  Functions of the prelude are not user code, not reported
        '__scbi_known="$(compgen -A function | tr "\\n" " ")"',
        seed(svars),
        #  as in the Bash driver, the status of a sourced file is ignored
        #  (only an explicit exit stops)
        *[f"source {quote(str(f))}" for f in files],
        _DUMP,
    ]
    env = dict(base_env or {})
    env.update(svars.environ())
    proc = subprocess.run(
        ["bash", "-s"],
        input=("\n".join(script) + "\n").encode(errors="surrogateescape"),
        cwd=cwd,
        env=env,
        capture_output=True,
    )
    if proc.returncode != 0:
        out = (proc.stdout + proc.stderr).decode(errors="replace")
        raise BashEvalError(out.strip(), proc.returncode, out)

    result = ShellVars()
    items = proc.stdout.decode(errors="surrogateescape").split("\0")
    for kind, name, exported, value in zip(items[0::4], items[1::4], items[2::4], items[3::4]):
        if kind == "F":
            result.functions[name] = value
        elif kind == "R":
            if _BASH_ARRAYS.match(name):
                continue
            akind, _, key = exported.partition(":")
            entry = result.arrays.setdefault(name, (akind, {}))
            if _:
                entry[1][key] = value
        elif not BASH_INTERNAL.match(name):
            result.set(name, value, export=exported == "1")
    return result


_SIMPLE = re.compile(r"^[^$`\\'\"~*?\[\](){}<>|&;!]*$")


def eval_echo(value: str, svars: ShellVars, base_env: Mapping[str, str] | None = None) -> str:
    """Result of ``eval echo <value>`` (used for ini values).

    Values without any shell meta-character are handled directly.
    """
    if _SIMPLE.match(value):
        return " ".join(words(value))
    env = dict(base_env or {})
    env.update(svars.environ())
    proc = subprocess.run(
        ["bash", "-s", "--", value],
        input=f"{seed(svars)}\neval echo \"$1\"\n",
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.stdout.rstrip("\n")
