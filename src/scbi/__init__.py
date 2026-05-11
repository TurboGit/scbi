from .auto_variant import resolve_auto_variant, check_os_package
from .build_env import BuildEnv
from .core import ScbiBuild, main, CANONICAL_STEPS
from .hook_executor import HookExecutor, apply_env_operation, merge_env_dict
from .ini_config import IniConfig, load_module_env, parse_env_file
from .models import (
    InheritMapping,
    ModuleRef,
    ParsedHookKey,
    Plan,
    PlanEntry,
    Plugin,
    RefKind,
    PlanError,
    PlanNotFoundError,
    PlanSyntaxError,
    PluginError,
    PluginNotFoundError,
    PluginSyntaxError,
)
from .plan_reader import PlanReader
from .plugin_loader_yaml import PluginLoader, parse_hook_key, SCBI_BASE_HOOKS, ENV_HOOKS
from .store import Store

__all__ = [
    "BuildEnv",
    "CANONICAL_STEPS",
    "HookExecutor",
    "IniConfig",
    "InheritMapping",
    "ModuleRef",
    "ParsedHookKey",
    "Plan",
    "PlanEntry",
    "Plugin",
    "PluginLoader",
    "PlanReader",
    "RefKind",
    "SCBI_BASE_HOOKS",
    "ENV_HOOKS",
    "ScbiBuild",
    "Store",
    "PlanError",
    "PlanNotFoundError",
    "PlanSyntaxError",
    "PluginError",
    "PluginNotFoundError",
    "PluginSyntaxError",
    "apply_env_operation",
    "load_module_env",
    "parse_env_file",
    "merge_env_dict",
    "main",
    "parse_hook_key",
]
