from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .build_env import BuildEnv
from .hook_executor import HookExecutor
from .models import ModuleRef, Plugin, RefKind
from .plan_reader import PlanReader
from .plugin_loader_yaml import PluginLoader
from .source_manager import SourceManager

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

    def _ilog(self, module: str, msg: str) -> None:
        print(f"[{module}] {msg}", file=sys.stderr)

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

        self._ilog(ref.module, f"building {ref}")
        self._ilog(ref.module, f"  variant = {be.variant}")
        self._ilog(ref.module, f"  target  = {be.scbi_target}")
        self._ilog(ref.module, f"  prefix  = {be.scbi_prefix}")
        self._ilog(ref.module, f"  TVDIR   = {be.tvdv_dir}")

        modules_list = self._get_modules(plugin, be)
        if modules_list is not None:
            return self._build_meta(plugin, be, executor, modules_list, ref)

        self._run_env_phase(executor, plugin, be)

        sm = SourceManager(self.plugin_loader, be)
        code = sm.handle_sources(plugin, ref)
        if code != 0:
            print(
                f"scbi: error: source handling failed for {ref}",
                file=sys.stderr,
            )
            return code

        for step in CANONICAL_STEPS:
            code = self._run_step(executor, plugin, be, step)
            if code != 0:
                print(
                    f"scbi: step '{step}' failed with code {code}",
                    file=sys.stderr,
                )
                return code

        return 0

    def _get_modules(
        self, plugin: Plugin, be: BuildEnv
    ) -> list[str] | None:
        resolved = self.plugin_loader.resolve_hook(
            plugin, be.variant, "modules"
        )
        if resolved is not None and isinstance(resolved, list):
            return [be.substitute(m.strip()) for m in resolved if m.strip()]
        return None

    def _build_meta(
        self,
        plugin: Plugin,
        be: BuildEnv,
        executor: HookExecutor,
        modules_list: list[str],
        ref: ModuleRef,
    ) -> int:
        self._ilog(be.module, f"  meta-module: {modules_list}")

        resolved_agg = self.plugin_loader.resolve_hook(
            plugin, be.variant, "aggregate"
        )

        self._run_env_phase(executor, plugin, be)

        for child_ref in modules_list:
            code = self.build(child_ref)
            if code != 0:
                return code

        if resolved_agg is not None:
            agg_text = resolved_agg
            if isinstance(agg_text, list):
                agg_text = " ".join(agg_text)
            agg_text = be.substitute(str(agg_text))
            self._ilog(be.module, f"  aggregate: {agg_text}")

        return 0

    def _run_env_phase(
        self, executor: HookExecutor, plugin: Plugin, be: BuildEnv
    ) -> None:
        hooks = plugin.hooks

        if "external-env" in hooks:
            env_dict = hooks["external-env"]
            if isinstance(env_dict, dict):
                executor.accumulate_env(env_dict)

        resolved = self.plugin_loader.resolve_hook(plugin, be.variant, "env")
        if resolved is not None and isinstance(resolved, dict):
            executor.accumulate_env(resolved)

        resolved_be = self.plugin_loader.resolve_hook(
            plugin, be.variant, "build-env"
        )
        if resolved_be is not None and isinstance(resolved_be, dict):
            executor.accumulate_env(resolved_be)

    def _resolve_config_options(
        self, plugin: Plugin, be: BuildEnv
    ) -> str:
        results = self.plugin_loader.resolve_all_hooks(
            plugin, be.variant, "config-options"
        )
        if not results:
            return ""

        tokens: list[str] = []
        for r in results:
            if isinstance(r, list):
                for item in r:
                    substituted = be.substitute(item)
                    tokens.append(substituted)
        return " ".join(tokens)

    def _is_out_of_tree(self, plugin: Plugin, be: BuildEnv) -> bool:
        resolved = self.plugin_loader.resolve_hook(
            plugin, be.variant, "out-of-tree"
        )
        if resolved is not None:
            if isinstance(resolved, list) and resolved:
                val = resolved[0].strip().lower()
                return val in ("true", "yes")
        return True

    def _setup_source_dir(
        self, plugin: Plugin, be: BuildEnv
    ) -> None:
        shared_src = be.module_root / "src"
        variant_src = be.src_dir

        if shared_src.exists() or shared_src.is_symlink():
            variant_src.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "rsync", "-a", "--delete",
                    str(shared_src) + "/",
                    str(variant_src) + "/",
                ],
                capture_output=True,
            )

    def _setup_build_dir(
        self, plugin: Plugin, be: BuildEnv, oot: bool
    ) -> None:
        build_dir = be.build_dir
        src_dir = be.src_dir

        if oot:
            build_dir.mkdir(parents=True, exist_ok=True)
        else:
            if build_dir.is_symlink():
                build_dir.unlink()
            elif build_dir.exists():
                if build_dir.is_dir():
                    shutil.rmtree(str(build_dir), ignore_errors=True)
                else:
                    build_dir.unlink()
            if src_dir.exists():
                rel = os.path.relpath(src_dir, build_dir.parent)
                os.symlink(rel, str(build_dir))

    def _is_source_unchanged(self, be: BuildEnv) -> bool:
        var_sid = be.module_root / f"source-id-{be.variant}"
        latest_sid = be.module_root / "source-id"
        tvdv_sid = be.tvdv_dir / "source-id"

        if not var_sid.exists():
            return False

        if tvdv_sid.exists():
            return _file_eq(var_sid, tvdv_sid)
        elif latest_sid.exists():
            return _file_eq(var_sid, latest_sid)
        return False

    def _is_build_cached(self, be: BuildEnv) -> bool:
        var_bid = be.module_root / f"build-id-{be.variant}"
        tvdv_bid = be.tvdv_dir / "build-id"
        if var_bid.exists() and tvdv_bid.exists():
            return _file_eq(var_bid, tvdv_bid)
        return False

    def _update_build_cache(self, be: BuildEnv) -> None:
        var_bid = be.module_root / f"build-id-{be.variant}"
        tvdv_bid = be.tvdv_dir / "build-id"
        if var_bid.exists():
            shutil.copy2(str(var_bid), str(tvdv_bid))

    def _write_build_id(self, be: BuildEnv, vid: str) -> None:
        raw = f"{be.scbi_prefix}:{be.scbi_target}:{be.module}:{vid}"
        bid = hashlib.md5(raw.encode()).hexdigest()
        path = be.module_root / f"build-id-{be.variant}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bid)

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

        log_path = be.logs_dir / f"{step}.log"
        cmd_path = be.logs_dir / f"{step}.cmd"

        if step == "setup":
            oot = self._is_out_of_tree(plugin, be)

            if not pre_hook and not main_hook and not post_hook:
                self._setup_source_dir(plugin, be)
                self._setup_build_dir(plugin, be, oot)
                return 0

            self._ilog(be.module, f"  step '{step}' starting")

            if pre_hook is not None and isinstance(pre_hook, list):
                code = executor.run_commands_logged(
                    pre_hook, log_path, cmd_path, f"pre-{step}"
                )
                if code != 0:
                    return code

            self._setup_source_dir(plugin, be)
            self._setup_build_dir(plugin, be, oot)

            if main_hook is not None and isinstance(main_hook, list):
                code = executor.run_commands_logged(
                    main_hook, log_path, cmd_path, step,
                    cwd=be.src_dir,
                )
                if code != 0:
                    return code

            if post_hook is not None and isinstance(post_hook, list):
                code = executor.run_commands_logged(
                    post_hook, log_path, cmd_path, f"post-{step}"
                )
                if code != 0:
                    return code
            return 0

        if pre_hook is None and main_hook is None and post_hook is None:
            return 0

        self._ilog(be.module, f"  step '{step}' starting")

        if pre_hook is not None and isinstance(pre_hook, list):
            code = executor.run_commands_logged(
                pre_hook, log_path, cmd_path, f"pre-{step}"
            )
            if code != 0:
                return code

        if main_hook is not None:
            commands = main_hook
            if isinstance(commands, list):
                if step == "config":
                    if self._is_source_unchanged(be):
                        self._ilog(be.module, "  config skipped (source unchanged)")
                        return 0
                    config_opts = self._resolve_config_options(plugin, be)
                    commands = [
                        cmd.replace("$CONFIG_OPTIONS", config_opts)
                        for cmd in commands
                    ]
                elif step in ("build", "install"):
                    if self._is_build_cached(be):
                        self._ilog(be.module, f"  {step} skipped (build cached)")
                        return 0

                cwd = be.build_dir if step in ("config", "build") else be.src_dir
                code = executor.run_commands_logged(
                    commands, log_path, cmd_path, step,
                    cwd=cwd,
                )
                if code != 0:
                    return code

                if step == "install":
                    self._update_build_cache(be)

        if post_hook is not None and isinstance(post_hook, list):
            code = executor.run_commands_logged(
                post_hook, log_path, cmd_path, f"post-{step}"
            )
            if code != 0:
                return code

        return 0


def _file_eq(a: Path, b: Path) -> bool:
    try:
        return a.read_text() == b.read_text()
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    args = list(argv)

    for a in args:
        if a in ("--help", "-h"):
            print(
                "Usage: scbi <module>[/<variant>][:<version>] [options]",
                file=sys.stderr,
            )
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
