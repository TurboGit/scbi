"""Execution of hooks in Bash.

Each hook runs in its own Bash process (as each module was handled in its
own sub-shell by the Bash driver) containing:

- the driver functions needed by the runtime (compat.sh) and the runtime
  functions and settings (scbi.hooks.runtime),
- the shell variables of the hook environment (exported ones are passed
  as the process environment) and its functions (e.g. module-final-step
  from an environment file),
- the driver state read by the runtime helpers (SCBI_MODVER,
  SCBI_MODULES_LIST, SCBI_MODULES_DIR, SCBI_OS_DISCRIMINANTS...),
- the functions of the loaded plug-ins: Bash definitions for legacy
  plug-ins, YAML hooks rendered as Bash functions (needed when Bash code
  calls them, e.g. get-config-options from a config script).

:meth:`HookShell.run` runs a command hook (output given line by line),
:meth:`HookShell.capture` a value hook (output lines) and
:meth:`HookShell.env` an environment hook of a legacy plug-in (the changes
it makes to the shell variables are applied to the context environment).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from scbi.bashenv import BASH_INTERNAL, ShellVars, quote, seed
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import _select
from scbi.hooks.runtime import Runtime
from scbi.plugin import catalog
from scbi.plugin.lift import parse_hook_name
from scbi.plugin.model import EnvOp, EnvOps, Function, Shell, Values


class HookError(Exception):
    pass


# --------------------------------------------------------- rendering


def _assoc(name: str, values: dict[str, str]) -> str:
    items = " ".join(f"[{quote(k)}]={quote(v)}" for k, v in values.items())
    return f"declare -gA {name}=({items})"


def _dq(text: str) -> str:
    """Double quoted Bash word keeping $ expansions."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`") + '"'


def _params(names) -> str:
    return "".join(f"    local {p}=${i}\n" for i, p in enumerate(names, 1))


def _env_action_bash(op: EnvOp) -> str:
    a = op.args
    if op.verb == "import":
        return f"eval $({a[0]})"
    if op.verb == "export":
        return f"export {a[0]}={_dq(a[1])}"
    if op.verb == "local":
        return f"local {a[0]}={_dq(a[1])}"
    if op.verb == "assign":
        return f"{a[0]}={_dq(a[1])}"
    if op.verb == "mkdir":
        return "mkdir -p " + " ".join(_dq(x) for x in a)
    return " ".join([op.verb] + [_dq(x) for x in a])


def render(name: str, obj, ctx: HookContext | None, plugin: str = "") -> str:
    """Bash definition of the namespace entry ``name``.

    Guards and values of YAML hooks are evaluated for ``ctx``.
    """
    if isinstance(obj, str):
        return obj
    if isinstance(obj, Function):
        return f"function {name}()\n{{\n{_params(obj.params)}{obj.script or 'true'}\n}}"
    key = parse_hook_name(plugin, name) if plugin else None
    params = catalog.spec(key.hook).params if key else catalog.STD_PARAMS
    if isinstance(obj, Shell):
        return f"function {name}()\n{{\n{_params(params)}{obj.script or 'true'}\n}}"
    if isinstance(obj, Values):
        #  items expanded by Bash when called (parameters bound at call)
        items = list(_select(obj.items, ctx)) if ctx else [i for i in obj.items if isinstance(i, str)]
        lines = "".join(f"    printf '%s\\n' {_dq(v)}\n" for v in items)
        return f"function {name}()\n{{\n{_params(params)}{lines}    true\n}}"
    if isinstance(obj, EnvOps):
        body = "".join(f"    {_env_action_bash(op)}\n" for op in _select(obj.ops, ctx)) if ctx else ""
        return f"function {name}()\n{{\n{_params(params)}{body}    true\n}}"
    raise HookError(f"cannot render {name}: {type(obj).__name__}")


# ------------------------------------------------------------- shell


@dataclass
class Result:
    returncode: int
    output: str = ""


#  Scalar variables with their export flag, on file descriptor 3
_DUMP = r"""
for __scbi_v in $(compgen -v); do
    [[ $__scbi_v == __scbi_* ]] && continue
    __scbi_d=$(declare -p $__scbi_v 2>/dev/null) || continue
    __scbi_a=${__scbi_d#declare -}
    __scbi_a=${__scbi_a%% *}
    [[ $__scbi_a == *[aA]* ]] && continue
    __scbi_x=0
    [[ $__scbi_a == *x* ]] && __scbi_x=1
    printf '%s\0%s\0%s\0' "$__scbi_v" "$__scbi_x" "${!__scbi_v}" >&3
done
printf 'END\0' >&3
"""


def _parse_dumps(data: bytes) -> list[dict[str, tuple[str, bool]]]:
    dumps: list[dict[str, tuple[str, bool]]] = []
    current: dict[str, tuple[str, bool]] = {}
    items = data.decode(errors="surrogateescape").split("\0")
    i = 0
    while i < len(items) - 1:
        if items[i] == "END":
            dumps.append(current)
            current = {}
            i += 1
            continue
        current[items[i]] = (items[i + 2], items[i + 1] == "1")
        i += 3
    return dumps


class HookShell:
    """Build and run the Bash process of a hook."""

    def __init__(self, runtime: Runtime, namespace: dict[str, object], base_env: dict[str, str] | None = None):
        self.runtime = runtime
        self.namespace = namespace
        self.base_env = dict(base_env or {})

    def script(self, ctx: HookContext, call: str) -> str:
        rt = self.runtime.vars
        parts = ["shopt -s extglob", self.runtime.compat]
        parts += rt.functions.values()
        #  Runtime settings (1_setup...), then the hook environment
        parts.append(seed(ShellVars(rt.values, rt.exported)))
        parts.append(seed(ctx.env.vars))
        #  Driver state read by the runtime helpers
        parts.append(_assoc("SCBI_MODVER", ctx.plan.modver))
        parts.append(_assoc("SCBI_MODULE_ALIAS", ctx.plan.module_alias))
        parts.append(_assoc("SCBI_OS_DISCRIMINANTS", {d: "yes" for d in ctx.discriminants}))
        #  Associative arrays of the driver, always declared
        arrays = {"SCBI_MODULES_DIR": {}, **ctx.arrays}
        for name, values in arrays.items():
            parts.append(_assoc(name, values))
        parts.append(f"SCBI_MODULES_LIST=({' '.join(quote(m) for m in ctx.modules_list)})")
        parts.append(f"SCBI_HOST={quote(ctx.host)}; SCBI_TARGET={quote(ctx.target)}")
        #  Plug-ins functions
        for name, obj in self.namespace.items():
            owner = ctx.module if name.startswith(f"{ctx.module}-") else ""
            parts.append(render(name, obj, ctx, owner))
        parts.append(call)
        return "\n".join(parts) + "\n"

    @staticmethod
    def call_line(function: str, args: list[str]) -> str:
        return " ".join([function] + [quote(a) for a in args])

    def _environ(self, ctx: HookContext) -> dict[str, str]:
        env = dict(self.base_env)
        env.update(ctx.env.environ())
        return env

    def run(self, ctx: HookContext, function: str, args: list[str],
            on_line: Callable[[str], None] | None = None) -> Result:
        """Run a command hook; its output (stdout and stderr) is given line
        by line to ``on_line`` or returned."""
        script = self.script(ctx, self.call_line(function, args))
        #  the script is read entirely before running, the hook gets an
        #  empty standard input
        proc = subprocess.Popen(
            ["bash", "-c", 'eval "$(cat)"'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=ctx.cwd, env=self._environ(ctx),
        )
        assert proc.stdin and proc.stdout
        proc.stdin.write(script.encode(errors="surrogateescape"))
        proc.stdin.close()
        lines: list[str] = []
        for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip("\n")
            if on_line is not None:
                on_line(line)
            else:
                lines.append(line)
        return Result(proc.wait(), "\n".join(lines))

    def capture(self, ctx: HookContext, function: str, args: list[str]) -> list[str]:
        """Output lines of a value hook (standard error ignored)."""
        script = self.script(ctx, self.call_line(function, args) + " 2>/dev/null")
        proc = subprocess.run(["bash", "-c", 'eval "$(cat)"'],
                              input=script.encode(errors="surrogateescape"),
                              capture_output=True, cwd=ctx.cwd, env=self._environ(ctx))
        text = proc.stdout.decode(errors="replace")
        return text.split("\n")[:-1] if text else []

    def env(self, ctx: HookContext, function: str, args: list[str]) -> Result:
        """Run an environment hook; the changes it makes to the shell
        variables are applied to ``ctx.env``."""
        call = f"{_DUMP}\n{self.call_line(function, args)} > /dev/null 2>&1\n__scbi_rc=$?\n{_DUMP}\nexit $__scbi_rc"
        script = self.script(ctx, call)
        proc = subprocess.run(["bash", "-c", 'exec 3>&1 1>/dev/null; eval "$(cat)"'],
                              input=script.encode(errors="surrogateescape"),
                              capture_output=True, cwd=ctx.cwd, env=self._environ(ctx))
        dumps = _parse_dumps(proc.stdout)
        if len(dumps) != 2:
            raise HookError(f"{function}: environment hook failed: {proc.stderr.decode(errors='replace')}")
        before, after = dumps
        values, exported = ctx.env.vars.values, ctx.env.vars.exported
        for name, (value, x) in after.items():
            if BASH_INTERNAL.match(name):
                continue
            if before.get(name) != (value, x):
                values[name] = value
                if x:
                    exported.add(name)
                else:
                    exported.discard(name)
        for name in before:
            if name not in after and not BASH_INTERNAL.match(name):
                values.pop(name, None)
                exported.discard(name)
        return Result(proc.returncode)
