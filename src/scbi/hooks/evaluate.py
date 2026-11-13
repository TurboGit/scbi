"""Evaluation of declarative hooks (plug-in definitions): values and environment
actions, with their guard conditions."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from scbi.bashenv import BASH_INTERNAL, BashEvalError, source_files
from scbi.hooks import builtins
from scbi.hooks.context import HookContext
from scbi.hooks.expand import expand
from scbi.plugin import expr
from scbi.plugin.model import EnvOp, EnvOps, Guarded, Values


class EvalError(Exception):
    pass


_DEFINE_VAR = {
    "add-to-var": "ADD", "prepend-to-var": "PREPEND", "append-to-var": "APPEND",
    "remove-from-var": "REMOVE", "set-var": "SET",
}


class GuardContext:
    """scbi.plugin.expr.Context for a hook context."""

    def __init__(self, ctx: HookContext):
        self.ctx = ctx

    def variable(self, name: str) -> str | bool:
        c = self.ctx
        if name == "ref":
            return c.params.get("REF") or builtins.get_version(c)
        if name == "target":
            return c.params.get("TARGET") or c.target
        if name == "host":
            return c.host
        if name == "variant":
            return c.params.get("VARIANT") or c.variant
        if name == "kind":
            return c.params.get("KIND", "")
        if name == "cross":
            return c.host != c.target
        raise EvalError(f"unknown condition variable {name}")

    def function(self, name: str, arg: str) -> str | bool:
        c = self.ctx
        if name == "version":
            return builtins.get_module_version(c, arg)
        if name == "build-type":
            kind, _, default = arg.partition(",")
            return builtins.get_build_type(c, kind, default)
        if name == "enabled":
            return builtins.is_enabled(c, arg)[0]
        if name == "exists":
            return os.path.lexists(arg if os.path.isabs(arg) else c.cwd / arg)
        if name == "dir":
            if c.target_dir is None:
                raise EvalError("dir() is not available in this context")
            return c.target_dir(arg, "default")
        raise EvalError(f"unknown condition function {name}")

    def has_discriminants(self, discs: list[str]) -> bool:
        return all(d in self.ctx.discriminants for d in discs)

    def expand(self, value: str) -> str:
        return expand(value, self.ctx)


def _select(items, ctx: HookContext):
    """Items whose guards are true, flattened."""
    guard = GuardContext(ctx)
    for it in items:
        if isinstance(it, Guarded):
            if expr.evaluate(it.cond, guard):
                yield from _select(it.items, ctx)
        else:
            yield it


def eval_values(values: Values, ctx: HookContext) -> list[str]:
    """Output lines of a value hook."""
    return [expand(it, ctx) for it in _select(values.items, ctx)]


def apply_env(ops: EnvOps | tuple, ctx: HookContext, base_env: dict[str, str] | None = None) -> None:
    """Apply environment actions to ``ctx.env``."""
    env = ctx.env
    items = ops.ops if isinstance(ops, EnvOps) else ops
    for op in _select(items, ctx):
        assert isinstance(op, EnvOp)
        verb = op.verb
        if verb == "import":
            _import(op.args[0], ctx, base_env)
            continue
        args = [expand(a, ctx) for a in op.args]
        if verb in _DEFINE_VAR:
            action = _DEFINE_VAR[verb]
            env.define_var(action, args[0], args[1])
        elif verb == "define-var":
            env.define_var(args[0], args[1], args[2])
        elif verb == "unset-var":
            env.unset_var(args[0])
        elif verb == "export":
            env.export(op.args[0], args[1])
        elif verb == "local":
            ctx.locals[op.args[0]] = args[1]
        elif verb == "assign":
            ctx.locals.pop(op.args[0], None)
            env.vars.values[op.args[0]] = args[1]
        elif verb == "system-compiler":
            env.system_compiler()
        elif verb in ("target-env", "no-target-env"):
            prefix, target = (args + ["", ""])[:2]
            fct = env.target_env if verb == "target-env" else env.no_target_env
            fct(prefix, target, host=ctx.host, bdir=ctx.scbi_bdir)
        elif verb == "mkdir":
            for d in args:
                (Path(d) if os.path.isabs(d) else ctx.cwd / d).mkdir(parents=True, exist_ok=True)
        else:
            raise EvalError(f"unknown environment action {verb}")


def _import(command: str, ctx: HookContext, base_env: dict[str, str] | None) -> None:
    """``eval $(command)``: run the command, evaluate its output."""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(f"eval $({command})\n")
        script = f.name
    try:
        res = source_files([script], ctx.env.vars, cwd=ctx.cwd, base_env=base_env)
    except BashEvalError as e:
        raise EvalError(f"import {command}: {e}") from None
    finally:
        os.unlink(script)
    old = ctx.env.vars
    #  Variables owned by Bash are not imported back: keep the current ones
    for name, value in old.values.items():
        if BASH_INTERNAL.match(name):
            res.set(name, value, export=name in old.exported)
    res.functions = old.functions
    ctx.env.vars = res
