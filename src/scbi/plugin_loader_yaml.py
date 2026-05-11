from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    InheritMapping,
    ParsedHookKey,
    Plugin,
    PluginError,
    PluginNotFoundError,
    PluginSyntaxError,
)

ENV_HOOKS = {"env", "build-env", "tests-env", "external-env"}

SCBI_BASE_HOOKS: list[str] = [
    "build-depends",
    "tests-depends",
    "config-options",
    "external-env",
    "build-env",
    "tests-env",
    "propagate-version",
    "only-explicit-build",
    "out-of-tree",
    "plan",
    "vcs",
    "archive",
    "patches",
    "version",
    "modules",
    "aggregate",
    "depends",
    "env",
    "setup",
    "config",
    "build",
    "install",
    "wrapup",
    "prefix",
    "tests",
    "run",
]

KNOWN_HOOKS_SET = set(SCBI_BASE_HOOKS)


def parse_hook_key(key: str) -> ParsedHookKey:
    sorted_hooks = sorted(KNOWN_HOOKS_SET, key=lambda h: -len(h))

    base_hook = None
    for hook in sorted_hooks:
        if key == hook:
            base_hook = hook
            prefix = ""
            break
        if key.endswith(f"-{hook}"):
            base_hook = hook
            prefix = key[: -len(hook) - 1]
            break

    if base_hook is None:
        raise PluginSyntaxError(f"Cannot parse hook key: {key}")

    cross = False
    modifier = ""

    if not prefix:
        return ParsedHookKey(base_hook=base_hook)

    parts = prefix.split("-")

    if parts and parts[-1] == "cross":
        cross = True
        parts.pop()

    if parts and parts[-1] in ("pre", "post"):
        modifier = parts.pop()

    variant = "-".join(parts)

    return ParsedHookKey(
        variant=variant,
        modifier=modifier,
        cross=cross,
        base_hook=base_hook,
    )


def _is_env_hook(key: str) -> bool:
    try:
        parsed = parse_hook_key(key)
    except PluginSyntaxError:
        return False
    return parsed.base_hook in ENV_HOOKS


def _normalize_hook_value(key: str, value: Any) -> list[str] | dict:
    if _is_env_hook(key) and isinstance(value, dict):
        return value
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, dict):
        return [yaml.dump(value, default_flow_style=False).strip()]
    return [str(value)]


class PluginLoader:
    def __init__(self, plugin_dir: str | Path):
        self.plugin_dir = Path(plugin_dir)
        self._cache: dict[str, Plugin] = {}

    def load(self, name: str) -> Plugin:
        if name in self._cache:
            return self._cache[name]

        path = self._find_plugin_file(name)
        plugin = self._parse_yaml(path)
        self._resolve_inheritance(plugin)
        self._cache[name] = plugin
        return plugin

    def _find_plugin_file(self, name: str) -> Path:
        candidates = [
            self.plugin_dir / f"{name}.yaml",
            self.plugin_dir / f"{name}.yml",
            self.plugin_dir / name,
        ]
        for p in candidates:
            if p.is_file():
                return p
        raise PluginNotFoundError(
            f"Plugin '{name}' not found in {self.plugin_dir}"
        )

    def _parse_yaml(self, path: Path) -> Plugin:
        raw = path.read_text()
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise PluginSyntaxError(
                f"Plugin file {path} must contain a dict"
            )

        name = data.get("name")
        if not name:
            name = path.stem

        hooks: dict[str, list[str] | dict] = {}
        variants: set[str] = set()
        raw_hooks = data.get("hooks", {})
        if not isinstance(raw_hooks, dict):
            raise PluginSyntaxError(
                f"hooks must be a dict in plugin {name}"
            )

        for key, value in raw_hooks.items():
            normalized = _normalize_hook_value(key, value)
            hooks[key] = normalized
            try:
                parsed = parse_hook_key(key)
            except PluginSyntaxError:
                continue
            if parsed.variant:
                variants.add(parsed.variant)

        inherit = data.get("inherit")
        inherit_mappings = None
        raw_mappings = data.get("inherit-mapping")
        if raw_mappings:
            if isinstance(raw_mappings, dict):
                raw_mappings = [raw_mappings]
            inherit_mappings = []
            for m in raw_mappings:
                inherit_mappings.append(
                    InheritMapping(
                        no_variant=m.get("no-variant", False),
                        hooks=m.get("hooks"),
                        name=m.get("name"),
                    )
                )

        modules = data.get("modules")
        vcs = data.get("vcs")
        out_of_tree = data.get("out-of-tree")
        prefix = data.get("prefix")
        aliases = data.get("aliases", {})

        if out_of_tree is None and "out-of-tree" in raw_hooks:
            val = raw_hooks["out-of-tree"]
            if isinstance(val, bool):
                out_of_tree = val

        if vcs is None and "vcs" in raw_hooks:
            val = raw_hooks["vcs"]
            if isinstance(val, dict):
                vcs = val

        if prefix is None and "prefix" in raw_hooks:
            val = raw_hooks["prefix"]
            if isinstance(val, str):
                prefix = val

        if modules is None and "modules" in raw_hooks:
            val = raw_hooks["modules"]
            if isinstance(val, list):
                modules = val

        return Plugin(
            name=name,
            hooks=hooks,
            variants=variants,
            inherit=inherit,
            inherit_mappings=inherit_mappings,
            modules=modules,
            vcs=vcs,
            out_of_tree=out_of_tree,
            prefix=prefix,
            aliases=aliases,
        )

    def _resolve_inheritance(self, plugin: Plugin) -> None:
        if not plugin.inherit:
            return

        parents = (
            [plugin.inherit]
            if isinstance(plugin.inherit, str)
            else list(plugin.inherit)
        )

        inherit_mappings = plugin.inherit_mappings or []

        # child's own hooks (always kept)
        child_hooks = dict(plugin.hooks)

        for parent_name in parents:
            parent = self.load(parent_name)

            mapping = None
            for m in inherit_mappings:
                if m.name:
                    if m.name == parent_name:
                        mapping = m
                        break
                elif mapping is None:
                    mapping = m

            for key, commands in parent.hooks.items():
                if key in child_hooks:
                    continue
                if mapping and mapping.no_variant:
                    try:
                        parsed = parse_hook_key(key)
                    except PluginSyntaxError:
                        continue
                    if parsed.variant:
                        continue
                if mapping and mapping.hooks:
                    try:
                        parsed = parse_hook_key(key)
                    except PluginSyntaxError:
                        continue
                    if parsed.base_hook not in mapping.hooks:
                        continue
                child_hooks[key] = commands

            for v in parent.variants:
                plugin.variants.add(v)

            if parent.modules:
                if plugin.modules is None:
                    plugin.modules = list(parent.modules)
                else:
                    for m in parent.modules:
                        if m not in plugin.modules:
                            plugin.modules.append(m)

        plugin.hooks = child_hooks

    def resolve_hook(
        self,
        plugin: Plugin,
        variant: str,
        hook_name: str,
        use_cross: bool = False,
    ) -> list[str] | dict | None:
        var_parts: list[str] = []
        if variant not in ("default", ""):
            var_parts = variant.split(".")

        search = var_parts if var_parts else ["default"]

        for v in search:
            key = self._internal_find_hook(plugin, v, hook_name, use_cross)
            if key:
                return plugin.hooks[key]

        key = self._internal_find_hook(plugin, "", hook_name, use_cross)
        if key:
            return plugin.hooks[key]

        return None

    def resolve_all_hooks(
        self,
        plugin: Plugin,
        variant: str,
        hook_name: str,
        use_cross: bool = False,
    ) -> list[list[str] | dict]:
        var_parts: list[str] = []
        if variant not in ("default", ""):
            var_parts = variant.split(".")

        results: list[list[str] | dict] = []
        var_found = False

        search_order: list[str] = ["common"]
        search_order.extend(var_parts)
        if not var_parts:
            search_order.append("default")

        for v in search_order:
            key = self._internal_find_hook(plugin, v, hook_name, use_cross)
            if key:
                if v not in ("common", "default"):
                    var_found = True
                results.append(plugin.hooks[key])

        if not var_found:
            key = self._internal_find_hook(plugin, "", hook_name, use_cross)
            if key:
                results.append(plugin.hooks[key])

        return results

    @staticmethod
    def _internal_find_hook(
        plugin: Plugin,
        variant: str,
        hook_name: str,
        use_cross: bool,
    ) -> str | None:
        if not variant:
            if use_cross:
                cross_key = f"cross-{hook_name}"
                if cross_key in plugin.hooks:
                    return cross_key
            if hook_name in plugin.hooks:
                return hook_name
            return None

        if use_cross:
            v_cross = f"{variant}-cross-{hook_name}"
            if v_cross in plugin.hooks:
                return v_cross
            base_cross = f"cross-{hook_name}"
            if base_cross in plugin.hooks:
                return base_cross

        direct = f"{variant}-{hook_name}"
        if direct in plugin.hooks:
            return direct

        return None

    def get_hook_names(self, plugin: Plugin) -> list[str]:
        return list(plugin.hooks.keys())
