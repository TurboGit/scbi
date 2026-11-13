"""Running a command hook of a YAML plug-in (a body in the command
language) with the interpreter (scbi.hooks.cmdlang): its context
(parameters, plug-in variables, config-options, callable functions),
its isolated environment (steps.hookenv) and its replay file."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.cmdlang import Runner, State
from scbi.plugin import catalog
from scbi.plugin.lift import parse_hook_name
from scbi.plugin.model import Commands, Function
from scbi.steps import replay
from scbi.steps.hookenv import hook_environment


def is_commands(builder, fct: str) -> bool:
    """The hook function ``fct`` is a body of the command language."""
    return isinstance(builder.d.registry.functions.get(fct), Commands)


def _owner(registry, name: str):
    """(module, HookKey) of a hook function name, the longest loaded module
    name first (a module name may contain dashes)."""
    for m in sorted(registry.loaded, key=len, reverse=True):
        key = parse_hook_name(m, name)
        if key is not None:
            return m, key
    return None, None


class Hook:
    """A command hook of module ``module`` / ``variant`` called as
    ``fct args`` from ``cwd``; ``sv``: the driver variables of the module
    (its environment included)."""

    def __init__(self, builder, module: str, variant: str, fct: str, args: list[str], cwd: str,
                 sv: ShellVars | None = None):
        self.b = builder
        self.d = builder.d
        self.module = module
        self.variant = variant
        self.fct = fct
        self.args = args
        self.cwd = cwd
        self.sv = sv if sv is not None else self.d.sv
        reg = self.d.registry
        self.body: Commands = reg.functions[fct]
        owner, key = _owner(reg, fct)
        self.hook = key.hook if key else fct[len(module) + 1:]
        self.plugin = owner or module
        self.params = dict(zip(catalog.spec(self.hook).params, args)) if key else {}

    # ------------------------------------------------------------ context

    def config_options(self) -> list[str]:
        prefix, target, variant = (self.args + ["", "", ""])[:3]
        return self.d.runner().variant_values(self.module, variant or self.variant, "config-options",
                                              [prefix, target, variant], self.d.plan, self.b.modules_list)

    def functions(self) -> dict[str, tuple[tuple[str, ...], tuple]]:
        """The functions callable by name: the plug-in functions and the
        command hooks (e.g. inherited with --name)."""
        reg = self.d.registry
        funcs = {}
        for name, obj in reg.functions.items():
            if isinstance(obj, Function):
                funcs[name] = (obj.params, obj.ast)
            elif isinstance(obj, Commands):
                _, key = _owner(reg, name)
                params = catalog.spec(key.hook).params if key else catalog.STD_PARAMS
                funcs[name] = (params, obj.ast)
        return funcs

    def environment(self) -> dict[str, str]:
        return hook_environment(self.sv.environ(), self.d.environ)

    def where(self) -> str:
        path = self.d.registry.plugin_file(self.plugin)
        return f"{path.name if path else self.plugin}: {self.hook}"

    # ---------------------------------------------------------------- run

    def run(self, out: Callable[[str], None], trace: Callable[[str], None] | None = None,
            err: Callable[[str], None] | None = None) -> int:
        """Run the hook, its output (text chunks) to ``out`` (and its errors
        to ``err``, default ``out``)."""
        ctx = self.b.ctx(self.module, self.variant, self.hook)
        ctx.env = Environment(ShellVars(dict(self.sv.values), set(self.sv.exported), dict(self.sv.functions)))
        ctx.params = dict(self.params)
        ctx.cwd = Path(self.cwd)
        runner = Runner(ctx, self.where(), config_options=self.config_options,
                        functions=self.functions(), trace=trace)
        state = State(dict(self.d.registry.variables), self.environment(), self.cwd, out,
                      out if err is None else err)
        return runner.run(self.body.ast, state)

    def write_replay(self, path: str) -> None:
        reg = self.d.registry
        functions = {}
        for name, obj in reg.functions.items():
            if isinstance(obj, Function):
                functions[name] = {"params": list(obj.params), "run": obj.script, "line": obj.line}
            elif isinstance(obj, Commands) and name != self.fct and not obj.is_nop():
                _, key = _owner(reg, name)
                params = catalog.spec(key.hook).params if key else catalog.STD_PARAMS
                functions[name] = {"params": list(params), "run": obj.script, "line": obj.line}
        file = reg.plugin_file(self.plugin)
        version = ""
        info = self.d.plan.module_ref(self.module)
        if len(info) > 3:
            version = info[3]
        r = replay.Replay(
            module=self.module, variant=self.variant, hook=self.hook, function=self.fct,
            plugin_file=str(file) if file else "", cwd=self.cwd,
            host=self.d.get("SCBI_HOST"), target=self.d.get("SCBI_TARGET"),
            run=self.body.script, line=self.body.line, params=dict(self.params),
            variables=dict(reg.variables),
            driver={k: v for k, v in self.sv.values.items() if k.startswith("SCBI_")},
            environment=self.environment(), config_options=self.config_options(),
            functions=functions, version=version)
        replay.write(path, r)
