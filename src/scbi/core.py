from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .auto_variant import resolve_auto_variant
from .build_env import BuildEnv
from .dependency_resolver import DependencyResolver
from .hook_executor import HookExecutor
from .models import ModuleRef, Plugin, RefKind
from .plan_reader import PlanReader
from .plugin_loader_yaml import PluginLoader
from .source_manager import SourceManager

SCBI_VERSION = "12.1"

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
        enabled_features: dict[str, str] | None = None,
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
        self.enabled_features = enabled_features or {}

        self.plan_reader: PlanReader | None = None
        self.plugin_loader: PluginLoader | None = None
        self.dependency_resolver: DependencyResolver | None = None
        self.do_deps: bool = False

        self.do_purge: bool = False
        self.do_purge_only: bool = False
        self.do_force: bool = False
        self.do_update: bool = False
        self.dry_run: bool = False
        self.stat_mode: str | None = None
        self.plan_name: str | None = None
        self.env_name: str | None = None
        self.ini_section: str | None = None
        self.no_patch: bool = False
        self.safe: bool = False
        self.clean_install: bool = False
        self.quiet: bool = False
        self.archive_mode: bool = False
        self.steps: list[str] = list(CANONICAL_STEPS)

    def _ensure_loaders(self) -> None:
        if self.plan_reader is None:
            self.plan_reader = PlanReader(self.plans_dir)
        if self.plugin_loader is None:
            self.plugin_loader = PluginLoader(self.plugins_dir)

    def _ilog(self, module: str, msg: str) -> None:
        import datetime as dt
        ts = dt.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        if self.quiet:
            return
        print(f"{ts} : {msg}", file=sys.stderr)

    def build(self, module_ref: str) -> int:
        self._ensure_loaders()

        ref = ModuleRef.parse(module_ref)

        if self.dry_run:
            self._ilog(ref.module, f"would build {ref}")
            return 0

        plugin = self.plugin_loader.load(ref.module)

        resolved_variant, auto_msg = resolve_auto_variant(
            self.plugin_loader, plugin, ref.variant, self.plugins_dir
        )
        if auto_msg:
            self._ilog(ref.module, f"  {auto_msg}")
        ref.variant = resolved_variant

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
            scbi_enabled_features=self.enabled_features,
        )

        if self.stat_mode:
            self._do_stat(be, plugin)
            return 0

        if self.do_purge_only:
            self._do_purge(be)
            return 0

        if self.do_purge:
            self._do_purge(be)

        be.ensure_dirs()

        executor = HookExecutor(be)

        disp_ref = ref.version if ref.version and ref.version != "NONE" else "master"
        variant_display = " ".join(be.variant.replace("default", "").split(".")).strip() or "default"
        self._ilog(ref.module, f"Building {ref.module} [{variant_display}] ({disp_ref})")
        if be.is_cross:
            self._ilog(ref.module, f"cross {be.scbi_target}")
        else:
            self._ilog(ref.module, f"native {be.scbi_target}")

        step_names = " ".join(self.steps) if self.steps != CANONICAL_STEPS else "setup config build install wrapup"
        self._ilog(ref.module, f"steps: {step_names}")

        modules_list = self._get_modules(plugin, be)
        if modules_list is not None:
            return self._build_meta(plugin, be, executor, modules_list, ref)

        if self.do_deps:
            if self.dependency_resolver is None:
                self.dependency_resolver = DependencyResolver(self)
            code = self.dependency_resolver.resolve(ref)
            if code != 0:
                return code

        self._run_env_phase(executor, plugin, be)

        sm = SourceManager(self.plugin_loader, be)
        code = sm.handle_sources(plugin, ref)
        if code != 0:
            print(
                f"scbi: error: source handling failed for {ref}",
                file=sys.stderr,
            )
            return code

        self._ilog(ref.module, "trigger: not yet built")

        if ref.variant.startswith("native"):
            self._ilog(ref.module, f"End Building {ref.module} [{variant_display}] ({disp_ref})")
            return 0

        for step in self.steps:
            if step not in CANONICAL_STEPS:
                continue
            code = self._run_step(executor, plugin, be, step)
            if code != 0:
                elog_msg = f"scbi: step '{step}' failed with code {code}"
                print(elog_msg, file=sys.stderr)
                return code

        self._ilog(ref.module, f"End Building {ref.module} [{variant_display}] ({disp_ref})")
        return 0

    def _do_purge(self, be: BuildEnv) -> None:
        self._ilog(be.module, "  purging build directory")
        tvdv = be.tvdv_dir
        if tvdv.exists():
            shutil.rmtree(str(tvdv), ignore_errors=True)

    def _do_stat(self, be: BuildEnv, plugin: Plugin) -> None:
        self._ilog(be.module, "  status:")
        source_id = be.module_root / f"source-id-{be.variant}"
        if source_id.exists():
            self._ilog(be.module, f"    source: {source_id.read_text().strip()}")
        build_id = be.module_root / f"build-id-{be.variant}"
        if build_id.exists():
            self._ilog(be.module, f"    build:  {build_id.read_text().strip()}")
        install_dir = be.install_dir
        if install_dir.exists():
            items = len(list(install_dir.rglob("*")))
            self._ilog(be.module, f"    install: {items} files")

    def _get_modules(
        self, plugin: Plugin, be: BuildEnv
    ) -> list[str] | None:
        resolved = self.plugin_loader.resolve_hook(
            plugin, be.variant, "modules", use_cross=be.is_cross
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
            plugin, be.variant, "aggregate", use_cross=be.is_cross
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
        use_cross = be.is_cross

        if "external-env" in hooks:
            env_dict = hooks["external-env"]
            if isinstance(env_dict, dict):
                executor.accumulate_env(env_dict)

        resolved = self.plugin_loader.resolve_hook(
            plugin, be.variant, "env", use_cross=use_cross
        )
        if resolved is not None and isinstance(resolved, dict):
            executor.accumulate_env(resolved)

        resolved_be = self.plugin_loader.resolve_hook(
            plugin, be.variant, "build-env", use_cross=use_cross
        )
        if resolved_be is not None and isinstance(resolved_be, dict):
            executor.accumulate_env(resolved_be)

    def _resolve_config_options(
        self, plugin: Plugin, be: BuildEnv
    ) -> str:
        results = self.plugin_loader.resolve_all_hooks(
            plugin, be.variant, "config-options", use_cross=be.is_cross
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
            plugin, be.variant, "out-of-tree", use_cross=be.is_cross
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
        use_cross = be.is_cross

        pre_key = f"pre-{step}"
        post_key = f"post-{step}"

        pre_hook = ld.resolve_hook(plugin, be.variant, pre_key, use_cross=use_cross)
        main_hook = ld.resolve_hook(plugin, be.variant, step, use_cross=use_cross)
        post_hook = ld.resolve_hook(plugin, be.variant, post_key, use_cross=use_cross)

        log_path = be.logs_dir / f"{step}.log"
        cmd_path = be.logs_dir / f"{step}.cmd"

        if step == "setup":
            oot = self._is_out_of_tree(plugin, be)

            if not pre_hook and not main_hook and not post_hook:
                self._setup_source_dir(plugin, be)
                self._setup_build_dir(plugin, be, oot)
                return 0

            self._ilog(be.module, f"{step} starting")

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

        self._ilog(be.module, f"{step} starting")

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
                    if not self.do_force and self._is_source_unchanged(be):
                        self._ilog(be.module, "config skipped (source unchanged)")
                        return 0
                    config_opts = self._resolve_config_options(plugin, be)
                    commands = [
                        cmd.replace("$CONFIG_OPTIONS", config_opts)
                        for cmd in commands
                    ]
                elif step in ("build", "install"):
                    if not self.do_force and self._is_build_cached(be):
                        self._ilog(be.module, f"{step} skipped (build cached)")
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

        self._ilog(be.module, f"{step} completed")
        return 0


def _file_eq(a: Path, b: Path) -> bool:
    try:
        return a.read_text() == b.read_text()
    except OSError:
        return False


def _parse_enable_flag(arg: str) -> tuple[str, str] | None:
    if arg.startswith("--enable-"):
        name = arg[len("--enable-"):]
        key = name.replace("-", "_")
        return (key, "true")
    return None


def _parse_ini_flag(arg: str) -> str | None:
    if arg.startswith("--ini="):
        return arg[len("--ini="):]
    if arg.startswith("--ini"):
        return ""
    return None


def _parse_eq_flag(arg: str, prefix: str) -> str | None:
    if arg.startswith(prefix + "="):
        return arg[len(prefix + "="):]
    return None


def _usage() -> None:
    print(
        "Usage: scbi [options] <module>[/<variant>][:<version>]",
        file=sys.stderr,
    )
    print("Options:", file=sys.stderr)
    print("  -h | --help              This help message", file=sys.stderr)
    print("  -v | --version           Display driver version", file=sys.stderr)
    print("  -q | --quiet             Do not display information log", file=sys.stderr)
    print("  -t | --prefix=<dir>      Install prefix", file=sys.stderr)
    print("  -b | --build-dir=<dir>   Build root directory", file=sys.stderr)
    print("  -j | --jobs=<n>          Parallel jobs", file=sys.stderr)
    print("  -S | --no-setup          Skip setup", file=sys.stderr)
    print("  -I | --no-install        Skip install", file=sys.stderr)
    print("  -W | --no-wrapup         Skip wrapup", file=sys.stderr)
    print("  -s | --setup             Do setup (reset steps)", file=sys.stderr)
    print("  -c | --config            Do config (reset steps)", file=sys.stderr)
    print("  -b | --build             Do build (reset steps)", file=sys.stderr)
    print("  -i | --install           Do install (reset steps)", file=sys.stderr)
    print("  -w | --wrapup            Do wrapup (reset steps)", file=sys.stderr)
    print("  -p | --purge[:only]      Remove build dir", file=sys.stderr)
    print("  -f | --force             Force rebuild", file=sys.stderr)
    print("  -u | --update            Update sources and rebuild", file=sys.stderr)
    print("  -d | --deps              Build dependencies first", file=sys.stderr)
    print("  -n | --no-patch          Do not apply patches", file=sys.stderr)
    print("  -e | --env=<name>        Environment file", file=sys.stderr)
    print("  -a | --create-archive    Build binary archive", file=sys.stderr)
    print("       --plan=<name>       Use a build plan", file=sys.stderr)
    print("       --target=<triple>   Target triplet", file=sys.stderr)
    print("       --host=<triple>     Host triplet", file=sys.stderr)
    print("       --plugins=<dir>     Plugins directory", file=sys.stderr)
    print("       --enable-<name>     Enable feature name", file=sys.stderr)
    print("       --flat              Flatter directory structure", file=sys.stderr)
    print("       --dry-run           Only list modules handled", file=sys.stderr)
    print("       --stat[:short|full] Display build status", file=sys.stderr)
    print("       --ini=<section>     Load ini file section", file=sys.stderr)
    print("       --safe              Clean build dir before configure", file=sys.stderr)
    print("       --clean-install     Clean install directory", file=sys.stderr)
    print("       --standalone        Standalone source archive", file=sys.stderr)
    print("       --clear-cache       Remove cached versions", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    args = list(argv)

    sb = ScbiBuild()
    step_specific = False

    i = 0
    while i < len(args):
        a = args[i]

        if a in ("--help", "-h"):
            _usage()
            return 0
        elif a in ("--version", "-v"):
            print(f"SCBI {SCBI_VERSION}", file=sys.stderr)
            return 0
        elif a in ("--quiet", "-q"):
            sb.quiet = True
            args.pop(i)
            continue
        elif a in ("--deps", "-d"):
            sb.do_deps = True
            args.pop(i)
            continue
        elif a in ("--force", "-f"):
            sb.do_force = True
            args.pop(i)
            continue
        elif a in ("--update", "-u"):
            sb.do_update = True
            args.pop(i)
            continue
        elif a in ("--dry-run",):
            sb.dry_run = True
            args.pop(i)
            continue
        elif a in ("--flat",):
            sb.flat = True
            args.pop(i)
            continue
        elif a in ("--no-patch", "-n"):
            sb.no_patch = True
            args.pop(i)
            continue
        elif a in ("--safe",):
            sb.safe = True
            args.pop(i)
            continue
        elif a in ("--clean-install",):
            sb.clean_install = True
            args.pop(i)
            continue
        elif a in ("--archive",):
            sb.archive_mode = True
            args.pop(i)
            continue
        elif a in ("--standalone",):
            sb.standalone = True
            args.pop(i)
            continue
        elif a.startswith("--enable-"):
            feat = _parse_enable_flag(a)
            if feat:
                sb.enabled_features[feat[0]] = feat[1]
            args.pop(i)
            continue
        elif a in ("--purge", "-p"):
            sb.do_purge = True
            args.pop(i)
            continue
        elif a == "--purge:only":
            sb.do_purge = False
            sb.do_purge_only = True
            args.pop(i)
            continue
        elif a.startswith("--stat"):
            rest = a[len("--stat"):]
            if rest.startswith(":"):
                sb.stat_mode = rest[1:] or "full"
            else:
                sb.stat_mode = "full"
            args.pop(i)
            continue
        elif a.startswith("--plan="):
            sb.plan_name = a[len("--plan="):]
            args.pop(i)
            continue
        elif a.startswith("--env="):
            sb.env_name = a[len("--env="):]
            args.pop(i)
            continue
        elif a.startswith("--ini"):
            val = _parse_ini_flag(a)
            if val is not None:
                sb.ini_section = val
            args.pop(i)
            continue
        elif a.startswith("--plugins="):
            sb.plugins_dir = Path(a[len("--plugins="):])
            args.pop(i)
            continue
        elif a.startswith("--build-dir="):
            sb.bdir = Path(a[len("--build-dir="):])
            args.pop(i)
            continue
        elif a.startswith("--prefix="):
            sb.prefix = Path(a[len("--prefix="):])
            args.pop(i)
            continue
        elif a.startswith("--target="):
            sb.target = a[len("--target="):]
            args.pop(i)
            continue
        elif a.startswith("--host="):
            sb.host = a[len("--host="):]
            args.pop(i)
            continue
        elif a.startswith("--jobs="):
            sb.jobs = int(a[len("--jobs="):])
            args.pop(i)
            continue
        elif a in ("--setup", "-s"):
            step_specific = True
            sb.steps.append("setup")
            args.pop(i)
            continue
        elif a in ("--config", "-c"):
            step_specific = True
            sb.steps.append("config")
            args.pop(i)
            continue
        elif a in ("--build", "-b"):
            step_specific = True
            sb.steps.append("build")
            args.pop(i)
            continue
        elif a in ("--install", "-i"):
            step_specific = True
            sb.steps.append("install")
            args.pop(i)
            continue
        elif a in ("--wrapup", "-w"):
            step_specific = True
            sb.steps.append("wrapup")
            args.pop(i)
            continue
        elif a in ("--no-setup", "-S"):
            sb.steps = [s for s in sb.steps if s != "setup"]
            args.pop(i)
            continue
        elif a in ("--no-install", "-I"):
            sb.steps = [s for s in sb.steps if s != "install"]
            args.pop(i)
            continue
        elif a in ("--no-wrapup", "-W"):
            sb.steps = [s for s in sb.steps if s != "wrapup"]
            args.pop(i)
            continue

        i += 1

    if step_specific:
        keep = set(sb.steps)
        sb.steps = [s for s in CANONICAL_STEPS if s in keep]

    if not args:
        _usage()
        return 1

    module_ref = args[0]

    return sb.build(module_ref)
