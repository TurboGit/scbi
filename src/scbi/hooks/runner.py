"""Calling the hooks of a module from the driver.

Value hooks of plug-in definitions (scbi.plugin.model) are evaluated in
Python. The selection of the hook functions
follows the Bash driver (scbi.plugin.resolve).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import eval_values, set_plugin_vars
from scbi.plan import PlanState
from scbi.plugin import catalog
from scbi.plugin.lift import parse_hook_name
from scbi.plugin.model import Values
from scbi.plugin.registry import Registry
from scbi.plugin.resolve import get_hook, variant_hooks


class HookRunner:
    def __init__(
        self,
        registry: Registry,
        svars: Callable[[], ShellVars],
        base_env: Callable[[], dict[str, str]],
        host: str,
        target: str,
        discriminants: Callable[[], list[str]],
        cwd: Path,
    ):
        self.registry = registry
        self.svars = svars
        self.base_env = base_env
        self.host = host
        self.target = target
        self.discriminants = discriminants
        self.cwd = cwd
        #  the directories of the modules of the build (SCBI_MODULES_DIR),
        #  given by the builder
        self.modules_dir: Callable[[], dict[str, str]] = dict

    @property
    def cross(self) -> bool:
        return self.host != self.target

    def context(self, module: str, variant: str, hook: str, args: list[str], plan: PlanState,
                modules_list: list[str] | None = None) -> HookContext:
        sv = self.svars()
        return HookContext(
            module=module, variant=variant, hook=hook,
            params=dict(zip(catalog.spec(hook).params, args)),
            env=Environment(ShellVars(dict(sv.values), set(sv.exported))),
            plan=plan, modules_list=list(modules_list or []), host=self.host, target=self.target,
            discriminants=frozenset(self.discriminants()), cwd=self.cwd,
            arrays={"SCBI_MODULES_DIR": dict(self.modules_dir())},
            scbi_bdir=sv.values.get("SCBI_BDIR", ""),
        )

    def call_value(self, function: str, module: str, variant: str, args: list[str],
                   plan: PlanState, modules_list: list[str] | None = None) -> list[str]:
        """Output lines of the value hook function ``function``."""
        key = parse_hook_name(module, function)
        hook = key.hook if key else "modules"
        ctx = self.context(module, variant, hook, args, plan, modules_list)
        obj = self.registry.functions.get(function)
        if not isinstance(obj, Values):
            raise TypeError(f"{function}: not a value hook")
        set_plugin_vars(ctx, self.registry.plugin_variables(module))
        return eval_values(obj, ctx)

    def hook_value(self, module: str, variant: str, hook: str, args: list[str],
                   plan: PlanState, modules_list: list[str] | None = None) -> str | None:
        """``$(FCT args)`` for the hook selected by get-hook (None if no hook)."""
        fct = get_hook(self.registry, module, variant, hook, self.cross)
        if not fct:
            return None
        return "\n".join(self.call_value(fct, module, variant, args, plan, modules_list))

    def variant_values(self, module: str, variant: str, hook: str, args: list[str],
                       plan: PlanState, modules_list: list[str] | None = None) -> list[str]:
        """Output lines of ``plugin-call-variant-hooks``."""
        lines: list[str] = []
        for fct in variant_hooks(self.registry, module, hook, variant, self.cross):
            lines += self.call_value(fct, module, variant, args, plan, modules_list)
        return lines
