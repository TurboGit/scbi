from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from .models import ModuleRef, RefKind

if TYPE_CHECKING:
    from .core import ScbiBuild
    from .build_env import BuildEnv
    from .plugin_loader_yaml import PluginLoader


DEPENDS_KINDS = ("build-depends", "depends", "tests-depends")


class DependencyResolver:
    def __init__(self, builder: ScbiBuild):
        self.builder = builder
        self.loader: PluginLoader = builder.plugin_loader
        self._loaded: dict[str, str] = {}
        self._rectree: list[str] = []
        self._checked: dict[str, bool] = {}

    def resolve(
        self,
        ref: ModuleRef,
        for_module: str = "@root",
        dep_kind: str | None = None,
    ) -> int:
        key = f"{ref.module}.{ref.variant}"
        if key in self._loaded:
            return 0

        plugin = self._try_load(ref.module)
        if plugin is None:
            if ref.module.startswith("os@"):
                self._ilog(ref.module, f"  {ref.module} OS package (skipped)")
                self._loaded[key] = "os"
                return 0
            self._ilog(ref.module, f"  {ref.module} plugin not found, treating as external")
            self._loaded[key] = "external"
            return 0

        modules_list = self._get_module_list(plugin, ref.variant)
        if modules_list is not None:
            self._loaded[key] = "meta"
            agg_text = self._get_aggregate(plugin, ref.variant)
            if agg_text:
                self._loaded[f"{key}.agg"] = agg_text
            return self._build_meta_children(modules_list, ref)

        self._loaded[key] = "final"

        if self._detect_cycle(ref.module):
            self._ilog(ref.module, f"recursive dependency detected for {ref.module}")
            self._print_cycle(ref.module)
            return 1

        self._rectree.append(ref.module)

        deps_order = [
            ("build-depends", "build"),
            ("depends", "default"),
            ("tests-depends", "tests"),
        ]
        for hook_name, kind in deps_order:
            if kind == "tests" and dep_kind != "tests":
                continue
            cdeps = self._get_depends(plugin, ref.variant, hook_name)
            if not cdeps:
                continue
            for dep_ref_str in cdeps:
                dep_ref = self._parse_dep(dep_ref_str)
                if dep_ref is None:
                    continue
                if dep_ref.module.startswith("os@"):
                    self._loaded.setdefault(
                        f"{dep_ref.module}.{dep_ref.variant}", "os"
                    )
                    continue
                ckey = f"{str(dep_ref)}:{kind}"
                if self._checked.get(ckey):
                    continue
                self._checked[ckey] = True

                code = self.resolve(dep_ref, ref.module, kind)
                if code != 0:
                    return code

                build_code = self.builder.build(str(dep_ref))
                if build_code != 0:
                    return build_code

        self._rectree.pop()

        return 0

    def _try_load(self, name: str):
        try:
            return self.loader.load(name)
        except Exception:
            return None

    def _get_depends(
        self, plugin, variant: str, hook_name: str
    ) -> list[str] | None:
        resolved = self.loader.resolve_hook(plugin, variant, hook_name)
        if resolved is not None and isinstance(resolved, list):
            return [m.strip() for m in resolved if m and m.strip()]
        return None

    def _get_module_list(self, plugin, variant: str) -> list[str] | None:
        resolved = self.loader.resolve_hook(plugin, variant, "modules")
        if resolved is not None and isinstance(resolved, list):
            return [m.strip() for m in resolved if m and m.strip()]
        return None

    def _get_aggregate(self, plugin, variant: str) -> str | None:
        resolved = self.loader.resolve_hook(plugin, variant, "aggregate")
        if resolved is None:
            return None
        if isinstance(resolved, list):
            return " ".join(resolved)
        return str(resolved)

    def _build_meta_children(self, modules: list[str], ref: ModuleRef) -> int:
        for child in modules:
            child_ref = (
                f"{child}/{ref.variant}" if ref.variant != "default" else child
            )
            code = self.builder.build(str(ModuleRef.parse(child_ref)))
            if code != 0:
                return code
        return 0

    def _parse_dep(self, dep_str: str) -> ModuleRef | None:
        dep_str = dep_str.strip()
        if not dep_str or dep_str.startswith("#"):
            return None
        try:
            return ModuleRef.parse(dep_str)
        except Exception:
            return None

    def _detect_cycle(self, module: str) -> bool:
        return module in self._rectree

    def _print_cycle(self, module: str) -> None:
        chain = " → ".join(self._rectree + [module])
        self._ilog(module, f"  dependency cycle: {chain}")

    def _ilog(self, module: str, msg: str) -> None:
        print(f"[{module}] {msg}", file=sys.stderr)
