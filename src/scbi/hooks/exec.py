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
from scbi.hooks.bashguard import to_bash
from scbi.hooks.runtime import Runtime
from scbi.plugin import catalog
from scbi.plugin.lift import parse_hook_name
from scbi.plugin.model import EnvOp, EnvOps, Function, Guarded, Shell, Values


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


def _block(items, emit, indent: str = "    ") -> str:
    """Bash lines for value/env items, guards translated to Bash."""
    out = []
    for it in items:
        if isinstance(it, Guarded):
            out.append(f"{indent}if {to_bash(it.cond)}; then\n")
            out.append(_block(it.items, emit, indent + "    ") or f"{indent}    true\n")
            out.append(f"{indent}fi\n")
        else:
            out.append(f"{indent}{emit(it)}\n")
    return "".join(out)


def render(name: str, obj, plugin: str = "") -> str:
    """Bash definition of the namespace entry ``name``.

    YAML hooks are rendered entirely in Bash: values are expanded and
    guards evaluated when the function is called (with its arguments), and
    environment actions call the runtime helpers, hence the visible
    ``define-var`` (which a user may have redefined).
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
        body = _block(obj.items, lambda v: f"printf '%s\\n' {_dq(v)}")
        return f"function {name}()\n{{\n{_params(params)}{body}    true\n}}"
    if isinstance(obj, EnvOps):
        body = _block(obj.ops, _env_action_bash)
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

    def __init__(
        self,
        runtime: Runtime,
        namespace: dict[str, object],
        base_env: dict[str, str] | None = None,
        loaded: dict[str, str] | None = None,
    ):
        """``namespace``: functions of the loaded plug-ins (Registry.functions),
        ``loaded``: SCBI_LOADED entries (Registry.loaded), the loaded
        plug-ins are not sourced again by load-module in the shell."""
        self.runtime = runtime
        self.namespace = namespace
        self.base_env = dict(base_env or {})
        self.loaded = dict(loaded or {})
        #  longest names first, to find the plug-in owning a function
        self._modules = sorted(self.loaded, key=len, reverse=True)

    def owner(self, name: str) -> str:
        """Plug-in owning the function ``name`` ("" for a custom function
        not prefixed by a loaded plug-in name)."""
        for m in self._modules:
            if name.startswith(f"{m}-"):
                return m
        return ""

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
        parts.append(_assoc("SCBI_LOADED", self.loaded))
        #  Associative arrays of the driver, always declared
        arrays = {"SCBI_MODULES_DIR": {}, **ctx.arrays}
        for name, values in arrays.items():
            parts.append(_assoc(name, values))
        parts.append(f"SCBI_MODULES_LIST=({' '.join(quote(m) for m in ctx.modules_list)})")
        parts.append(f"SCBI_HOST={quote(ctx.host)}; SCBI_TARGET={quote(ctx.target)}")
        #  Plug-ins functions
        for name, obj in self.namespace.items():
            parts.append(render(name, obj, self.owner(name)))
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


def run_env_hook(shell: HookShell, ctx: HookContext, function: str, args: list[str],
                 python_env: bool, base_env: dict[str, str] | None = None) -> None:
    """Apply the environment hook ``function`` to ``ctx.env``.

    A YAML hook is evaluated in Python when ``python_env`` is true (see
    scbi.hooks.policy); otherwise, and for legacy hooks, it runs in a hook
    shell, so that a redefined ``define-var`` applies.
    """
    from scbi.hooks.evaluate import apply_env

    obj = shell.namespace.get(function)
    if isinstance(obj, EnvOps) and python_env:
        spec_params = catalog.spec(parse_hook_name(shell.owner(function), function).hook).params \
            if shell.owner(function) else catalog.STD_PARAMS
        ctx.params = dict(zip(spec_params, args))
        apply_env(obj, ctx, base_env)
    else:
        shell.env(ctx, function, args)
