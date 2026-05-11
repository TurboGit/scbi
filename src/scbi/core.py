from __future__ import annotations

import sys
from pathlib import Path

from .build_env import BuildEnv
from .hook_executor import HookExecutor
from .models import ModuleRef, Plugin, RefKind
from .plan_reader import PlanReader
from .plugin_loader_yaml import PluginLoader

CANONICAL_STEPS = [
    "setup",
    "config",
    "build",
    "install",
    "wrapup",
]


class ScbiBuild:
    def __init__(
        self,
        plugins_dir: str | Path | None = None,
        plans_dir: str | Path | None = None,
        bdir: str | Path | None = None,
        prefix: str | Path | None = None,
        target: str | None = None,
        host: str | None = None,
        jobs: int = 0,
        flat: bool = False,
    ):
        cwd = Path.cwd()
        self.plugins_dir = Path(plugins_dir) if plugins_dir else cwd / "scripts.d"
        self.plans_dir = Path(plans_dir) if plans_dir else self.plugins_dir
        self.bdir = Path(bdir) if bdir else cwd / ".scbi-build"
        self.prefix = Path(prefix) if prefix else self.bdir / "install"
        self.target = target or ""
        self.host = host or ""
        self.jobs = jobs
        self.flat = flat

        self.plan_reader: PlanReader | None = None
        self.plugin_loader: PluginLoader | None = None

    def _ensure_loaders(self) -> None:
        if self.plan_reader is None:
            self.plan_reader = PlanReader(self.plans_dir)
        if self.plugin_loader is None:
            self.plugin_loader = PluginLoader(self.plugins_dir)

    def build(self, module_ref: str) -> int:
        self._ensure_loaders()

        ref = ModuleRef.parse(module_ref)

        plugin = self.plugin_loader.load(ref.module)

        be = BuildEnv(
            module=ref.module,
            variant=ref.variant,
            version=ref.version if ref.kind != RefKind.NONE else "NONE",
            scbi_bdir=self.bdir,
            scbi_prefix=self.prefix,
            scbi_target=self.target or "",
            scbi_host=self.host or "",
            scbi_plugins=self.plugins_dir,
            scbi_jobs=self.jobs,
            scbi_flat=self.flat,
        )

        be.ensure_dirs()

        executor = HookExecutor(be)

        print(f"scbi: building {ref}", file=sys.stderr)
        print(f"scbi:   variant = {be.variant}", file=sys.stderr)
        print(f"scbi:   target  = {be.scbi_target}", file=sys.stderr)
        print(f"scbi:   prefix  = {be.scbi_prefix}", file=sys.stderr)
        print(f"scbi:   TVDIR   = {be.tvdv_dir}", file=sys.stderr)

        self._run_env_phase(executor, plugin, be)

        for step in CANONICAL_STEPS:
            code = self._run_step(executor, plugin, be, step)
            if code != 0:
                print(f"scbi: step '{step}' failed with code {code}", file=sys.stderr)
                return code

        return 0

    def _run_env_phase(
        self, executor: HookExecutor, plugin: Plugin, be: BuildEnv
    ) -> None:
        hooks = plugin.hooks

        if "external-env" in hooks:
            env_dict = hooks["external-env"]
            if isinstance(env_dict, dict):
                executor.accumulate_env(env_dict)

        env_key = be.variant if be.variant != "default" else ""
        resolved = self.plugin_loader.resolve_hook(plugin, be.variant, "env")
        if resolved is not None and isinstance(resolved, dict):
            executor.accumulate_env(resolved)

        resolved_be = self.plugin_loader.resolve_hook(plugin, be.variant, "build-env")
        if resolved_be is not None and isinstance(resolved_be, dict):
            executor.accumulate_env(resolved_be)

    def _run_step(
        self,
        executor: HookExecutor,
        plugin: Plugin,
        be: BuildEnv,
        step: str,
    ) -> int:
        ld = self.plugin_loader

        pre_key = f"pre-{step}"
        post_key = f"post-{step}"

        pre_hook = ld.resolve_hook(plugin, be.variant, pre_key)
        main_hook = ld.resolve_hook(plugin, be.variant, step)
        post_hook = ld.resolve_hook(plugin, be.variant, post_key)

        if pre_hook is None and main_hook is None and post_hook is None:
            return 0

        print(f"scbi:   step '{step}'", file=sys.stderr)

        if pre_hook is not None and isinstance(pre_hook, list):
            code = executor.run_commands(pre_hook)
            if code != 0:
                return code

        if main_hook is not None:
            cwd = be.build_dir if step in ("config", "build") else be.src_dir
            if isinstance(main_hook, list):
                code = executor.run_commands(main_hook, cwd=cwd)
                if code != 0:
                    return code

        if post_hook is not None and isinstance(post_hook, list):
            code = executor.run_commands(post_hook)
            if code != 0:
                return code

        return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    args = list(argv)

    for a in args:
        if a in ("--help", "-h"):
            print("Usage: scbi <module>[/<variant>][:<version>] [options]", file=sys.stderr)
            print("Options:", file=sys.stderr)
            print("  --build-dir DIR   Build root directory", file=sys.stderr)
            print("  --prefix DIR      Install prefix", file=sys.stderr)
            print("  --target TRIPLE   Target triplet", file=sys.stderr)
            print("  --jobs N          Parallel jobs", file=sys.stderr)
            print("  --flat            Flatter directory structure", file=sys.stderr)
            return 0

    if not args:
        print("Usage: scbi <module>[/<variant>][:<version>]", file=sys.stderr)
        return 1

    module_ref = args[0]

    bdir = None
    prefix = None
    target = None
    host = None
    jobs = 0
    flat = False

    i = 1
    while i < len(args):
        a = args[i]
        if a == "--build-dir" and i + 1 < len(args):
            bdir = args[i + 1]
            i += 1
        elif a == "--prefix" and i + 1 < len(args):
            prefix = args[i + 1]
            i += 1
        elif a == "--target" and i + 1 < len(args):
            target = args[i + 1]
            i += 1
        elif a == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 1
        elif a == "--jobs" and i + 1 < len(args):
            jobs = int(args[i + 1])
            i += 1
        elif a == "--flat":
            flat = True
        i += 1

    sb = ScbiBuild(
        bdir=bdir,
        prefix=prefix,
        target=target,
        host=host,
        jobs=jobs,
        flat=flat,
    )

    return sb.build(module_ref)
