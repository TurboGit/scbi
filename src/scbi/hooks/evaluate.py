"""Evaluation of declarative hooks (plug-in definitions): values and environment
actions, with their guard conditions."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from scbi.bashcompat import ShellSyntaxError, shell_words
from scbi.hooks import builtins
from scbi.hooks.context import HookContext
from scbi.hooks.expand import expand
from scbi.plugin import expr
from scbi.plugin.model import EnvOp, EnvOps, Guarded, LocalAssign, SourceEntry, Values


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
            #  the KIND parameter (patches), else the kind of the module
            #  version in the build plan (DEV, BRANCH, VERSION...)
            if c.params.get("KIND"):
                return c.params["KIND"]
            info = c.plan.module_ref(c.module) if c.plan is not None else []
            return info[2] if len(info) > 2 else ""
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
        if name == "empty":
            return arg == ""
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


def set_plugin_vars(ctx: HookContext, variables: dict) -> dict[str, str | list[str]]:
    """Set the variables of the plug-in (``vars``) of the hook: each
    value expanded in the context of the hook, in order (a value may use
    the previous variables). A list (a tuple in the model) is expanded item
    by item, the empty items dropped: it is a list for the command hooks
    (the returned values), its items joined by blanks for the expansions
    of the values and environment actions (``ctx.plugin_vars``)."""
    ctx.plugin_vars = {}
    values: dict[str, str | list[str]] = {}
    for name, value in variables.items():
        if isinstance(value, (tuple, list)):
            items = [v for v in (expand(i, ctx) for i in value) if v != ""]
            values[name] = items
            ctx.plugin_vars[name] = " ".join(items)
        else:
            values[name] = ctx.plugin_vars[name] = expand(value, ctx)
    return values


def eval_values(values: Values, ctx: HookContext) -> list[str]:
    """Output lines of a value hook (a LocalAssign sets a variable of the
    following items)."""
    out: list[str] = []
    for it in _select(values.items, ctx):
        if isinstance(it, LocalAssign):
            ctx.locals[it.name] = expand(it.text, ctx)
        elif isinstance(it, SourceEntry):
            continue  # source-tree: eval_source_tree
        else:
            out.append(expand(it, ctx))
    return out


def eval_source_tree(values: Values, ctx: HookContext) -> list[SourceEntry]:
    """The entries of a source-tree hook selected by their guards, their
    fields expanded."""
    from scbi.plugin import construct

    out: list[SourceEntry] = []
    for it in _select(values.items, ctx):
        if isinstance(it, LocalAssign):
            ctx.locals[it.name] = expand(it.text, ctx)
        elif isinstance(it, SourceEntry):
            fields: dict = {"to": expand(it.to, ctx), "exclude": [expand(e, ctx) for e in it.exclude]}
            if it.from_:
                fields["from"] = expand(it.from_, ctx)
            out.append(construct.source_entry(fields))
    return out


def apply_env(ops: EnvOps | tuple, ctx: HookContext, base_env: dict[str, str] | None = None) -> None:
    """Apply environment actions to ``ctx.env``."""
    env = ctx.env
    items = ops.ops if isinstance(ops, EnvOps) else ops
    for op in _select(items, ctx):
        if isinstance(op, LocalAssign):
            ctx.locals[op.name] = expand(op.text, ctx)
            continue
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
        elif verb == "mkdir":
            for d in args:
                (Path(d) if os.path.isabs(d) else ctx.cwd / d).mkdir(parents=True, exist_ok=True)
        else:
            raise EvalError(f"unknown environment action {verb}")


_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)


def _import(command: str, ctx: HookContext, base_env: dict[str, str] | None) -> None:
    """``eval $(command)``: run the command (no shell), then apply the
    variable assignments, ``export`` and ``unset`` statements it prints
    (e.g. ``NAME='value'; export NAME;`` of ``opam env``)."""
    try:
        argv = [expand(w, ctx) for w in shell_words(command)]
    except ShellSyntaxError as e:
        raise EvalError(f"import {command}: {e}") from None
    env = {**(base_env or {}), **ctx.env.vars.environ()}
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=ctx.cwd, env=env)
    except OSError as e:
        raise EvalError(f"import {command}: {e.strerror}") from None
    #  unquoted $(...): the output words joined with a space, then parsed
    lexer = shlex.shlex(" ".join(proc.stdout.split()), posix=True, punctuation_chars=";")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as e:
        raise EvalError(f"import {command}: {e}") from None
    statements: list[list[str]] = [[]]
    for tok in tokens:
        if tok and set(tok) == {";"}:
            statements.append([])
        else:
            statements[-1].append(tok)
    for st in statements:
        if not st:
            continue
        if st[0] in ("export", "unset"):
            for arg in st[1:]:
                m = _ASSIGN.match(arg)
                if st[0] == "unset":
                    ctx.env.vars.values.pop(arg, None)
                    ctx.env.vars.exported.discard(arg)
                else:
                    ctx.env.export(m.group(1), m.group(2)) if m else ctx.env.export(arg)
            continue
        for arg in st:
            m = _ASSIGN.match(arg)
            if not m:
                raise EvalError(f"import {command}: unsupported statement {' '.join(st)!r}")
            ctx.env.vars.values[m.group(1)] = m.group(2)
