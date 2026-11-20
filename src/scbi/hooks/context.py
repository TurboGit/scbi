"""State in which a hook is evaluated."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scbi.env import Environment
from scbi.plan import PlanState


@dataclass
class HookContext:
    #  Plug-in the hook belongs to (the "caller" plug-in of the runtime
    #  helpers, e.g. for get-build-type or get-version)
    module: str
    variant: str
    #  Catalog hook name (env, build-env, config-options, config...)
    hook: str
    #  Hook parameters by name (PREFIX, TARGET, VARIANT, KIND, REF...)
    params: dict[str, str] = field(default_factory=dict)
    env: Environment = field(default_factory=Environment)
    plan: PlanState = field(default_factory=PlanState)
    #  SCBI_MODULES_LIST: modules being handled, the last one is current
    modules_list: list[str] = field(default_factory=list)
    host: str = ""
    target: str = ""
    discriminants: frozenset[str] = frozenset()
    cwd: Path = field(default_factory=Path.cwd)
    #  get-target-dir MODULE VARIANT, for the dir(<module>) condition
    target_dir: Callable[[str, str], str] | None = None
    scbi_bdir: str = ""
    #  Associative arrays readable as ${NAME[key]} (SCBI_MODULES_DIR)
    arrays: dict[str, dict[str, str]] = field(default_factory=dict)
    #  Variables local to the hook (``local`` environment action)
    locals: dict[str, str] = field(default_factory=dict)
    #  Variables of the plug-in (``vars``, expanded: set_plugin_vars)
    plugin_vars: dict[str, str] = field(default_factory=dict)

    def lookup(self, name: str) -> str:
        """Value of variable ``name``: local variable or hook parameter,
        else variable of the plug-in, else shell variable."""
        if name in self.locals:
            return self.locals[name]
        if name in self.params:
            return self.params[name]
        if name in self.plugin_vars:
            return self.plugin_vars[name]
        if name == "PWD":
            #  maintained by Bash: the current directory of the hook
            return str(self.cwd)
        return self.env.get(name)
