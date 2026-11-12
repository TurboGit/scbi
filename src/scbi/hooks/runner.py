"""Calling the hooks of a module from the driver.

Value hooks of YAML plug-ins are evaluated in Python, legacy (Bash) hooks
in a hook shell (scbi.hooks.exec). The selection of the hook functions
follows the Bash driver (scbi.plugin.resolve).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import eval_values
from scbi.hooks.exec import HookShell
from scbi.hooks.runtime import Runtime
from scbi.plan import PlanState
from scbi.plugin import catalog
from scbi.plugin.lift import parse_hook_name
from scbi.plugin.model import Values
from scbi.plugin.registry import Registry
from scbi.plugin.resolve import get_hook, variant_hooks


class HookRunner:
    def __init__(
        self,
        runtime: Runtime,
        registry: Registry,
        svars: Callable[[], ShellVars],
        base_env: Callable[[], dict[str, str]],
        host: str,
        target: str,
        discriminants: Callable[[], list[str]],
        cwd: Path,
    ):
        self.runtime = runtime
        self.registry = registry
        self.svars = svars
        self.base_env = base_env
        self.host = host
        self.target = target
        self.discriminants = discriminants
        self.cwd = cwd

    @property
    def cross(self) -> bool:
        return self.host != self.target

    def context(self, module: str, variant: str, hook: str, args: list[str], plan: PlanState,
                modules_list: list[str] | None = None) -> HookContext:
        sv = self.svars()
        return HookContext(
            module=module, variant=variant, hook=hook,
            params=dict(zip(catalog.spec(hook).params, args)),
            env=Environment(ShellVars(dict(sv.values), set(sv.exported), dict(sv.functions))),
            plan=plan, modules_list=list(modules_list or []), host=self.host, target=self.target,
            discriminants=frozenset(self.discriminants()), cwd=self.cwd,
            scbi_bdir=sv.values.get("SCBI_BDIR", ""),
        )

    def shell(self) -> HookShell:
        return HookShell(self.runtime, self.registry.functions, self.base_env(),
                         loaded=self.registry.scbi_loaded())

    def call_value(self, function: str, module: str, variant: str, args: list[str],
                   plan: PlanState, modules_list: list[str] | None = None) -> list[str]:
        """Output lines of the value hook function ``function``."""
        key = parse_hook_name(module, function)
        hook = key.hook if key else "modules"
        ctx = self.context(module, variant, hook, args, plan, modules_list)
        obj = self.registry.functions.get(function)
        if isinstance(obj, Values):
            return eval_values(obj, ctx)
        return self.shell().capture(ctx, function, args)

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
