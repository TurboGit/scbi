"""Handling of a module: sources, up-to-date check, environment, steps,
global install (port of handle-module and its helpers from the scbi
driver).

Everything runs in Python (no Bash): the sources (scbi.sources), the
environment of the module and its dependencies (scbi.steps.modenv), the
steps and their logs (scbi.steps.wrapper, scbi.steps.generic, the
command hooks interpreted by scbi.steps.interp).
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scbi import steptime
from scbi.bashcompat import assoc_keys, words
from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.errors import Exit, NotImplementedYet
from scbi.hooks.context import HookContext
from scbi.modref import is_host_prefixed, strip_host
from scbi.plugin.model import Commands
from scbi.plugin.resolve import get_hook
from scbi.sources import handle as sources
from scbi.sources.buildid import build_id
from scbi.sources.data import archive_exists, vcs_data
from scbi.steps import generic as generic_steps
from scbi.steps import interp
from scbi.steps.final import FinalStep
from scbi.steps import wrapper as step_wrapper
from scbi.vercmp import VERSION_ERROR, VERSION_OK, check_versions, get_version_number
from scbi.walker import Walker

#  is-module-up-to-date statuses
V_MATCHING, SRC_CHANGED, V_NOT_MATCHING, V_CANNOT_GET, V_ERROR = 0, 1, 2, 3, 4
B_FORCED, B_NOTYET, B_NOT_UPTODATE, V_NATIVE, V_NATIVE_MATCHING = 5, 6, 7, 8, 9

UPTODATE_MESSAGES = {
    SRC_CHANGED: ("trigger: sources changed", True),
    V_NOT_MATCHING: ("trigger: versions not matching", True),
    V_CANNOT_GET: ("trigger: cannot get version", True),
    V_ERROR: ("trigger: version error", True),
    B_FORCED: ("trigger: forced", False),
    B_NOTYET: ("trigger: not yet built", True),
    B_NOT_UPTODATE: ("trigger: build not up-to-date", True),
}


def _read_first_line(path: Path) -> str:
    """read-content: first line of a file ("" if missing)."""
    try:
        with open(path) as f:
            return f.readline().rstrip("\n")
    except OSError:
        return ""


def _same(a: Path, b: Path) -> bool:
    """diff -q a b succeeds."""
    try:
        return Path(a).read_bytes() == Path(b).read_bytes()
    except OSError:
        return False


class Builder:
    def __init__(self, driver):
        self.d = driver
        self.modules_list: list[str] = []
        self.handled: set[str] = set()
        #  the host@ dependencies built for the host in this run
        self.host_built: set[str] = set()
        self.modules_dir: dict[str, str] = {}
        #  the value hooks see the directories of the modules too
        driver.runner().modules_dir = lambda: self.modules_dir
        self.flatdir: dict[str, str] = {}
        self.ftdir = 1
        #  the sources fetched ahead (--update:prefetch: scbi.sources.prefetch)
        self.prefetcher = None

    # ------------------------------------------------------------ helpers

    def get(self, name: str) -> str:
        return self.d.get(name)

    def set(self, name: str, value: str) -> None:
        self.d.set(name, value)

    def out(self, line: str) -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    def ilog(self, module: str, *msg: str, tee: str | None = None) -> None:
        self.d.log.ilog(module, *msg, tee=tee)

    def elog(self, module: str, *msg: str) -> None:
        self.d.log.elog(module, *msg)

    def ctx(self, module: str, variant: str, hook: str = "config") -> HookContext:
        """Context of the driver shell: the driver variables are the
        environment (changes are applied back by env_code)."""
        d = self.d
        return HookContext(
            module=module, variant=variant, hook=hook,
            env=Environment(d.sv), plan=d.plan, modules_list=list(self.modules_list),
            host=self.get("SCBI_HOST"), target=self.get("SCBI_TARGET"),
            discriminants=frozenset(d.discriminants), cwd=Path.cwd(),
            arrays={"SCBI_MODULES_DIR": dict(self.modules_dir)},
            scbi_bdir=self.get("SCBI_BDIR"),
        )

    def final_step(self, hook, ctx) -> None:
        """``module-final-step`` of the environment file (an
        error in it is reported, the build goes on as with Bash)."""
        sys.stdout.flush()
        try:
            hook(ctx)
        except Exception as e:  # noqa: BLE001 - the user's code
            self.elog(ctx.module, "module_final_step:", f"{type(e).__name__}:", str(e))
        sys.stdout.flush()

    def module_environment(self, module: str, variant: str, calls, hook: str = "config") -> int:
        """The environment setup of a module applied to the driver
        variables: ``calls`` of scbi.steps.modenv.ModuleEnv.run (a
        ``module-env`` call ending with ``record`` has its output appended
        to $SCBI_ENV_MODULE, which is then unset). Returns the status."""
        from scbi.steps import modenv

        d = self.d
        sys.stdout.flush()
        me = modenv.ModuleEnv(self)
        rc = me.run(calls)
        d.sv = me.env.vars
        if any(c[-1] == "record" for c in calls):
            d.sv.values.pop("SCBI_ENV_MODULE", None)
            d.sv.exported.discard("SCBI_ENV_MODULE")
        return rc

    def module_env(self, calls) -> ShellVars:
        """The driver variables after the environment setup ``calls`` (see
        module_environment) run on a copy: the driver is not changed (a
        sub-shell in Bash)."""
        from scbi.steps import modenv

        me = modenv.ModuleEnv(self, Environment(self.d.sv.copy()))
        saved = dict(self.modules_dir)
        try:
            me.run(calls, out=lambda line: None)
        finally:
            self.modules_dir = saved
        return me.env.vars

    def fn_exists(self, name: str) -> bool:
        """A function of the loaded plug-ins."""
        return name in self.d.registry.functions

    def target_dir(self, module: str, variant: str, file: str = "") -> str:
        """Port of ``get-target-dir``."""
        bdir, target = self.get("SCBI_BDIR"), self.get("SCBI_TARGET")
        tdf = f"{bdir}/{module}/{target}-{variant}"
        lnk = self.get("SCBI_LNK")
        if self.get("DO_FLAT") == "yes":
            key = f"{module}-{variant}"
            val = self.flatdir.get(key, "")
            if val:
                pass
            elif os.path.islink(tdf):
                val = os.path.realpath(tdf)
                self.flatdir[key] = val
            elif os.path.isfile(tdf + lnk):
                val = os.path.realpath(f"{bdir}/{module}/{_read_first_line(Path(tdf))}")
                self.flatdir[key] = val
            else:
                while os.path.isdir(f"{bdir}/{self.ftdir}"):
                    self.ftdir += 1
                val = f"{bdir}/{self.ftdir}"
                os.makedirs(f"{bdir}/{module}", exist_ok=True)
                shutil.rmtree(tdf, ignore_errors=True)
                os.symlink(f"../{self.ftdir}", tdf)
                self.flatdir[key] = val
        else:
            val = tdf
            if os.path.islink(tdf):
                real = os.path.realpath(tdf)
                shutil.rmtree(real, ignore_errors=True)
                os.unlink(tdf)
        return val + (f"/{file}" if file else "")

    def is_host_dep(self, modref: str) -> bool:
        """A ``host@`` dependency in a cross build: the build of the module
        for the host is used (in a native build it is the module itself)."""
        return is_host_prefixed(modref) and self.get("SCBI_HOST") != self.get("SCBI_TARGET")

    def host_dir(self, module: str, variant: str, file: str = "") -> str:
        """The target directory of the build of ``module`` for the host (no
        change made, the flat link followed)."""
        tdf = f"{self.get('SCBI_BDIR')}/{module}/{self.get('SCBI_HOST')}-{variant}"
        val = os.path.realpath(tdf) if os.path.islink(tdf) else tdf
        return val + (f"/{file}" if file else "")

    def hook_value(self, module: str, variant: str, hook: str) -> str | None:
        tvdir = self.target_dir(module, variant)
        return self.d.runner().hook_value(module, variant, hook,
                                          [f"{tvdir}/install", self.get("SCBI_TARGET"), variant],
                                          self.d.plan, self.modules_list)

    def is_hook_true(self, module: str, variant: str, hook: str, default: str) -> bool:
        value = self.hook_value(module, variant, hook) or ""
        value = (value or default).upper()
        return value in ("TRUE", "YES")

    def load_module(self, module: str, variant: str) -> None:
        """Port of ``load-module``: plug-in loaded, meta/final recorded."""
        reg = self.d.registry
        reg.load_module(module)
        key = f"{module}.{variant}"
        if key not in reg.loaded:
            mods = self.d.runner().variant_values(
                module, variant, "modules", [self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), variant],
                self.d.plan, self.modules_list)
            if not "".join(mods).strip():
                reg.loaded[key] = "final"
            else:
                reg.loaded[key] = "meta"
                if get_hook(reg, module, variant, "aggregate", self.d.runner().cross):
                    #  $FCT $SCBI_PREFIX $SCBI_TARGET $variant
                    reg.loaded[f"{key}.agg"] = self.d.runner().hook_value(
                        module, variant, "aggregate",
                        [self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), variant],
                        self.d.plan, self.modules_list) or ""

    # -------------------------------------------------------- up-to-date

    def is_module_up_to_date(self, modref: str, formodule: str, module: str, variant: str, ref: str) -> int:
        """Port of ``is-module-up-to-date``."""
        bdir = Path(self.get("SCBI_BDIR"))
        #  check-archive-exists ... && kind=VERSION (kind is not used after)
        archive_exists(self, module, variant, ref)

        fct = get_hook(self.d.registry, module, variant, "version", self.d.runner().cross)
        if fct:
            tdir = tempfile.mkdtemp()
            cwd = os.getcwd()
            os.chdir(tdir)
            try:
                sv = self.module_env([
                    ("handle-build-depends-env", "@root", modref),
                    ("module-env", "@root", modref, "env"),
                    ("module-env", "@root", modref, "build-env")])
                chunks: list[str] = []
                interp.Hook(self, module, variant, fct,
                            [self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), variant], tdir, sv).run(
                    chunks.append, err=lambda text: None)
                mver = "".join(chunks).rstrip("\n")
            finally:
                os.chdir(cwd)
                shutil.rmtree(tdir, ignore_errors=True)
        else:
            mver = VERSION_OK

        tvdir = Path(self.target_dir(module, variant))
        mod_dir = bdir / module
        if (mod_dir / "source-id").is_file() and not (tvdir / "source-id").is_file():
            rsid = not _same(mod_dir / f"source-id-{variant}", mod_dir / "source-id")
        else:
            rsid = not _same(mod_dir / f"source-id-{variant}", tvdir / "source-id")

        #  get-version-number VAR $value: unquoted, first word only
        mver = get_version_number((words(mver) or [""])[0])
        nref = "0" if ref.upper() == "NONE" else get_version_number((words(ref) or [""])[0])

        if self.get("DO_FORCE") == "yes":
            (tvdir / "build-id").unlink(missing_ok=True)
            rbid = ebid = True
        else:
            ebid = not (tvdir / "build-id").is_file()
            rbid = not _same(mod_dir / f"build-id-{variant}", tvdir / "build-id")
            cache = self.get("SCBI_CACHE_DIR")
            if not ebid and rbid and cache:
                cf = _read_first_line(tvdir / "build-id")
                Path(cache, cf).unlink(missing_ok=True)

        cver = check_versions(nref, ">", mver)

        if variant == "native":
            return V_NATIVE if ebid else V_NATIVE_MATCHING
        if rsid and not ebid:
            return SRC_CHANGED
        if cver:
            return V_NOT_MATCHING
        if not mver:
            return V_CANNOT_GET
        if mver == VERSION_ERROR:
            return V_ERROR
        if rbid:
            if self.get("DO_FORCE") == "yes":
                return B_FORCED
            return B_NOTYET if ebid else B_NOT_UPTODATE
        return V_MATCHING

    # ------------------------------------------------------------ records

    def record_build_plan(self, module: str, variant: str) -> None:
        """Port of ``record-build-plan``."""
        from scbi.planview import list_build_plan

        path = Path(self.target_dir(module, variant)) / "logs" / "build-plan"
        path.write_text("# build plan\n" + "".join(f"{ln}\n" for ln in list_build_plan(self.d.plan)))

    def record_module_env(self, module: str, variant: str) -> None:
        """Port of ``record-module-env``."""
        log = Path(self.get("SCBI_LOGS"), self.get("TODAY"),
                   f"{self.get('SCBI_TARGET')}-{module}-{variant}-env.log")
        env = self.d.base_env()
        with open(log, "w") as f:
            f.write("==================== env \n")
            f.writelines(f"{k}={v}\n" for k, v in env.items())
        for tool, args in (("gprls", ["-v"]), ("gcc", ["-v"])):
            if shutil.which(tool, path=env.get("PATH")):
                with open(log, "a") as f:
                    f.write(f"==================== {tool} \n")
                    f.flush()
                    subprocess.run([tool, *args], stdout=f, stderr=f if tool == "gcc" else subprocess.DEVNULL,
                                   env=env)

    def write_env_cmd(self, module: str, variant: str, envtmp: Path) -> None:
        tvdir = self.target_dir(module, variant)
        logs_dir = f"{tvdir}/logs"
        path = Path(logs_dir, "env.cmd")
        path.unlink(missing_ok=True)
        out: list[str] = []
        if os.path.isdir(tvdir):
            out += ["", "# SCBI global settings"]
            for name, value in self.d.base_env().items():
                if not name.startswith("SCBI_"):
                    continue
                if name in ("SCBI_JOBS", "SCBI_HALF_JOBS"):
                    line = f"export {name}=${{{name}:-{value}}}"
                elif name == "SCBI_PLUGINS":
                    line = f"export {name}='{logs_dir}'"
                else:
                    line = f"export {name}='{value}'"
                out.append(" ".join(words(line)))
        text = "\n".join(out) + ("\n" if out else "")
        text += envtmp.read_text() if envtmp.exists() else ""
        target, bdir = self.get("SCBI_TARGET"), self.get("SCBI_BDIR")
        lines = ["", "# SCBI_MODULES_DIR", "declare -A SCBI_MODULES_DIR=("]
        for key, v in self.modules_dir.items():
            v = v.replace(target, "$SCBI_TARGET", 1)
            v = v[len(bdir):] if v.startswith(bdir) else v
            lines.append(f'  ["{key}"]="$SCBI_BDIR{v}"')
        lines.append(")")
        path.write_text(text + "\n".join(lines) + "\n")

    def triggered_by(self, module: str, drefs: Path, build_deps: Path) -> None:
        """Port of ``triggered-by``: dependencies whose build id changed."""
        if not (drefs.is_file() and build_deps.is_file()):
            return
        old = {ln.split()[0] for ln in build_deps.read_text().splitlines() if ln.split()}
        changed = []
        for ln in drefs.read_text().splitlines():
            f = ln.split()
            if f and f[0] not in old:
                changed.append(f)
        for f in sorted(changed, key=lambda f: f[1:] and f[1]):
            self.ilog(module, f"  ↳ {f[1] if len(f) > 1 else ''} changed")

    # -------------------------------------------------------------- prefix

    def handle_prefix(self, module: str, variant: str, ref: str, log: str) -> tuple[bool, str]:
        """Port of ``handle-prefix``: (success, install dir)."""
        tvdir = self.target_dir(module, variant)
        fct = get_hook(self.d.registry, module, variant, "prefix", self.d.runner().cross)
        if fct and self.get("SCBI_DEFAULT_PREFIX") == "yes":
            idir = self.hook_value(module, variant, "prefix") or ""
        else:
            idir = self.get("SCBI_PREFIX")
        if idir.upper() == "NONE":
            self.ilog(module, "skip global install")
            return True, idir
        if (ref.split(":", 1)[0] != "keep" and self.get("DO_INSTALL") != "no"
                and os.path.isdir(f"{tvdir}/install")):
            bdir, home = self.get("SCBI_BDIR"), self.get("HOME")
            idest = idir.replace(bdir, "<sandbox>", 1) if bdir else idir
            idest = idest.replace(home, "$HOME", 1) if home else idest
            self.ilog(module, "copy install into", idest)
            Path(bdir, module, f"install-{self.get('SCBI_TARGET')}-id").write_text(f"{variant}\n{idir}\n")
            sudo = []
            try:
                os.makedirs(idir, exist_ok=True)
            except OSError:
                sudo = ["sudo"]
            if not os.access(idir, os.W_OK):
                sudo = ["sudo"]
            subprocess.run([*sudo, "mkdir", "-p", f"{idir}/"])
            #  appended to the report log (not truncated)
            with open(log, "a") as f:
                rc = subprocess.run([*sudo, "rsync", "-a", "--force", f"{tvdir}/install/.", f"{idir}/."],
                                    stdout=f, stderr=f).returncode
            return rc == 0, idir
        return True, idir

    # ------------------------------------------------------------- module

    def handle_module(self, formodule: str, modref: str, depends_kind: str, is_aggregated: str) -> None:
        d = self.d
        info = d.plan.module_ref(modref, formodule)
        if len(info) > 4:
            self.elog(info[0], *info[4:])
            raise Exit(1)
        module, variant, kind, ref = (info + [""] * 4)[:4]

        d.set("SCBI_CURRENT_MODULE", module)

        key = f"{module}+{variant}+{ref}"
        if any(h.startswith(key) for h in self.handled):
            return
        self.handled.add(key)
        with open(self.get("SCBI_HANDLED"), "a") as f:
            f.write(key + "\n")

        if ref == "skip":
            self.ilog(module, "%BModule", f"%t{module}%c", "marked to be skipped")
            return

        #  the report log of the module (the driver messages, the output of
        #  the VCS and generic commands): one file per module and day
        log = str(d.log.report(module))
        d.set("log", log)
        os.chdir(self.get("SCBI_ROOT"))

        if d.registry.plugin_file(module) is None:
            self.out(f"error: no description for module {module}")
            raise Exit(1)

        self.load_module(module, variant)

        d.set("SCBI_ISOOT", "true")
        if not self.is_hook_true(module, variant, "out-of-tree", "TRUE"):
            d.set("SCBI_ISOOT", "false")

        if formodule != "@root" and self.is_hook_true(module, variant, "only-explicit-build", "FALSE"):
            self.progress_next(module, variant)
            self.ilog(module, "%BModule", f"%t{module}%c", "built only if explitly specified")
            return

        self.modules_list.append(module if variant == "default" else f"{module}/{variant}")
        try:
            self._handle_module(formodule, modref, depends_kind, is_aggregated,
                                module, variant, kind, ref, log)
        finally:
            self.modules_list.pop()

    def progress_next(self, module: str, variant: str) -> None:
        """The progress ``[n/N] module`` (scbi.log.Progress) when the module
        starts its own work: after its dependencies, so the module shown is
        the one being built."""
        progress = getattr(self.d, "progress", None)
        if progress is not None:
            progress.next(module if variant == "default" else f"{module}/{variant}")

    def _handle_module(self, formodule, modref, depends_kind, is_aggregated,
                       module, variant, kind, ref, log) -> None:
        d = self.d
        bdir = self.get("SCBI_BDIR")
        tvdir = self.target_dir(module, variant)
        os.makedirs(f"{tvdir}/logs", exist_ok=True)
        if self.get("DO_FLAT") == "yes":
            os.makedirs(f"{bdir}/{module}", exist_ok=True)

        if d.registry.loaded.get(f"{module}.{variant}") == "meta":
            #  in a sub-shell in Bash
            saved = (copy.deepcopy(d.sv), copy.deepcopy(d.plan), os.getcwd(), dict(self.modules_dir))
            try:
                res = self.handle_meta_module(formodule, module, variant, ref, depends_kind,
                                              is_aggregated, log)
            except Exit as e:
                res = e.status
            finally:
                d.sv, d.plan, cwd, self.modules_dir = saved
                os.chdir(cwd)
            if res != 0:
                raise Exit(1)
            return

        drefs = Path(bdir, module, f"build-deps-{variant}")
        drefs.unlink(missing_ok=True)

        if self.get("DEPS") == "yes":
            #  in a sub-shell in Bash
            saved = (copy.deepcopy(d.sv), os.getcwd())
            try:
                self.handle_all_depends(modref, module, variant, is_aggregated)
            finally:
                d.sv, cwd = saved
                os.chdir(cwd)
        else:
            self.check_host_depends(module, variant)

        self.progress_next(module, variant)

        if self.get("DRY_RUN") == "yes":
            self.out(modref)
            return

        d.log.clog(module)

        purge = self.get("DO_PURGE")
        if purge in ("yes", "only"):
            self.ilog(module, "%BPurging", f"%t{module}%c", "for", f"{self.get('SCBI_TARGET')}/{variant}")
            if os.path.isdir(f"{bdir}/{module}"):
                sys.stdout.flush()
                generic_steps.Generic(self, formodule, module, variant,
                                      self.target_dir(module, variant)).step("purge", None)

        if self.get("DO_CLEAN_INSTALL") == "yes":
            self.ilog(module, "Clean", module, "install for", f"{self.get('SCBI_TARGET')}/{variant}")
            if os.path.isdir(f"{bdir}/{module}"):
                sys.stdout.flush()
                generic_steps.Generic(self, formodule, module, variant, str(tvdir)).clean_install(
                    f"{tvdir}/install", self.get("SCBI_TARGET"))
            return

        if purge == "only":
            return

        disp = self.display_ref(module, variant, ref)

        d.log.line_sep()
        self.ilog(module, "%BBuilding", f"%t{module}%c", f"[%g{' '.join(variant.split('.'))}%c]",
                  f"(%g{disp}%c)")

        start = time.monotonic()

        if formodule != "@root":
            self.needed_by(module, log)

        if self.get("SCBI_HOST") == self.get("SCBI_TARGET"):
            self.ilog(module, "native", self.get("SCBI_TARGET"))
        else:
            self.ilog(module, "cross", self.get("SCBI_TARGET"))

        os.makedirs(tvdir, exist_ok=True)

        #  the module sub-shell: state restored afterwards
        saved = (copy.deepcopy(d.sv), dict(self.modules_dir), os.getcwd())
        try:
            res, is_uptodate = self.module_subshell(formodule, modref, depends_kind, is_aggregated,
                                                    module, variant, kind, ref, log, tvdir)
        finally:
            d.sv, self.modules_dir, cwd = saved
            os.chdir(cwd)
        if res != 0:
            raise Exit(1)

        if self.get("DO_ARCHIVE") == "yes":
            os.chdir(tvdir)
            for p in Path(tvdir).glob(f"{module}-bin.tar*"):
                p.unlink()
            subprocess.run(["tar", "cf", f"{module}-bin.tar", "--directory=install", "."])
            subprocess.run(["bzip2", "-9", f"{module}-bin.tar"])

        ok, idir = self.handle_prefix(module, variant, ref, log)
        if not ok:
            self.elog(module, "fail to copy to", idir)

        secs = int(time.monotonic() - start)
        if secs >= 5:
            self.ilog(module, "timing:", time.strftime("%H:%M:%S", time.gmtime(secs)))

        self.ilog(module, "End", "Building", module, f"[{' '.join(variant.split('.'))}]", f"({disp})")
        d.log.line_sep()

    # -------------------------------------------------------- meta-module

    def handle_meta_module(self, formodule: str, meta: str, variant: str, ref: str,
                           depends_kind: str, is_aggregated: str, log: str) -> int:
        """Port of ``handle-meta-module``; returns the status."""
        from scbi.plan import PlanLoader

        d = self.d
        bdir = self.get("SCBI_BDIR")
        mdir = f"{bdir}/{meta}"
        reg = d.registry
        cross = d.runner().cross
        vdisp = " ".join(variant.split("."))

        if get_hook(reg, meta, variant, "plan", cross):
            name = d.runner().hook_value(meta, variant, "plan", [self.get("SCBI_PLAN")], d.plan,
                                         self.modules_list) or ""
            first = (words(name) or [""])[0]
            PlanLoader(d.plan, Path(self.get("SCBI_PLUGINS")), d.discriminants, Path.cwd(),
                       d.is_built).load(first)

        self.record_build_plan(meta, variant)

        fct_setup = get_hook(reg, meta, variant, "setup", cross)
        fct_wrapup = get_hook(reg, meta, variant, "wrapup", cross)
        fct_agg = get_hook(reg, meta, variant, "aggregate", cross)

        agg_mode = "no"
        if fct_agg:
            #  $FCT_AGG $SCBI_PREFIX $TARGET $VARIANT ($TARGET: caller's global)
            agg_mode = d.runner().hook_value(
                meta, variant, "aggregate", [self.get("SCBI_PREFIX"), self.get("TARGET"), variant],
                d.plan, self.modules_list) or ""

        if self.get("DEPS") == "yes":
            #  The build dependencies of the meta-module are not in its
            #  modules: never aggregated
            for dmodule in self.get_all_depends(meta, variant, "build-depends"):
                if self.handle_depends(meta, dmodule, "build", "no") != 0:
                    return 1

        self.progress_next(meta, variant)
        start = time.monotonic()
        d.log.line_sep()
        self.ilog(meta, "%BMetamodule", f"%t{meta}%c", f"[%g{vdisp}%c]", "setup")
        if formodule != "@root":
            self.needed_by(formodule, log)

        def internal_wrapper(fct: str) -> int:
            if not fct:
                return 0
            return step_wrapper.StepWrapper(self, meta, variant).internal(f"{bdir}/install", fct)

        if internal_wrapper(fct_setup) != 0:
            return 1
        self.ilog(meta, "End", "metamodule", meta, f"[{vdisp}]", "setup")
        d.log.line_sep()

        do_agg_prefix = False
        tvmdir = ""
        if self.get("DEPS") == "yes" or (not fct_setup and not fct_wrapup):
            Path(mdir, "source-ref").unlink(missing_ok=True)
            tvmdir = self.target_dir(meta, variant)
            drefs = Path(bdir, meta, f"build-deps-{variant}")
            shutil.rmtree(f"{tvmdir}/install", ignore_errors=True)
            drefs.unlink(missing_ok=True)
            mods = d.runner().variant_values(
                meta, variant, "modules", [self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), variant],
                d.plan, self.modules_list)
            for m in words("\n".join(mods)):
                self.handle_module(meta, m, "default", agg_mode)
                info = (d.plan.module_ref(m, meta) + [""] * 4)[:4]
                mvariant, mref = info[1], info[3]
                self.record_dref(m, mvariant, drefs)
                if mref == "skip":
                    continue
                if fct_agg:
                    idir = self.target_dir(m, mvariant, "install")
                    if agg_mode != "no" and os.path.isdir(idir):
                        if agg_mode == "recursive":
                            self.sync_recursive(meta, variant, m, tvmdir, mdir)
                        else:
                            self.sync_dir(meta, variant, idir, f"{tvmdir}/.")
                    _append_file(Path(bdir, m, "source-ref"), Path(mdir, "source-ref"))
            do_agg_prefix = True

        is_utd = "no"
        tvdir = self.target_dir(meta, variant)
        os.chdir(mdir)
        Path(f"build-id-{variant}").write_text(
            build_id(self, self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), formodule, meta, variant))
        if _same(Path(f"build-id-{variant}"), Path(tvdir, "build-id")) and self.get("DO_FORCE") == "no":
            is_utd = "yes"
        else:
            #  written when the wrapup completed: an interrupted or failed
            #  wrapup is run again at the next run
            Path(tvdir, "build-id").unlink(missing_ok=True)

        d.log.line_sep()
        self.ilog(meta, "%BMetamodule", f"%t{meta}%c", f"[%g{vdisp}%c]", "wrapup")
        if formodule != "@root":
            self.needed_by(formodule, log)

        if is_utd == "no":
            if self.get("DO_FORCE") == "yes":
                self.ilog(meta, "trigger: forced")
            elif Path(tvdir, "build-deps").is_file():
                self.ilog(meta, "trigger: build not up-to-date")
                self.triggered_by(meta, Path(f"build-deps-{variant}"), Path(tvdir, "build-deps"))
            elif Path(f"build-deps-{variant}").is_file():
                self.ilog(meta, "trigger: not yet built")
            if internal_wrapper(fct_wrapup) != 0:
                return 1
            shutil.copy(f"build-id-{variant}", f"{tvdir}/build-id")

        if Path(f"build-deps-{variant}").is_file():
            shutil.copy(f"build-deps-{variant}", f"{tvdir}/build-deps")

        if agg_mode != "no" and do_agg_prefix:
            ok, idir = self.handle_prefix(meta, variant, ref, log)

        final = self.d.envfile.hook("module_final_step")
        if final is not None:
            mmode = "aggregate" if agg_mode != "no" else "yes"
            self.ilog(meta, "final", "step", "starting")
            self.final_step(final, FinalStep(self, f"{tvmdir}/install", self.get("SCBI_TARGET"), variant, meta,
                                             formodule, meta, depends_kind, mmode, is_aggregated, is_utd))
            self.ilog(meta, "final", "step", "completed")

        secs = int(time.monotonic() - start)
        if secs >= 5:
            self.ilog(meta, "timing:", time.strftime("%H:%M:%S", time.gmtime(secs)))
        self.ilog(meta, "End", "metamodule", meta, f"[{vdisp}]", "wrapup")
        d.log.line_sep()
        return 0

    # -------------------------------------------------------- dependencies

    def get_all_depends(self, module: str, variant: str, hook: str) -> list[str]:
        """Port of ``get-all-depends``."""
        reg = self.d.registry
        result = []
        values = self.d.runner().variant_values(
            module, variant, hook, [self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), variant],
            self.d.plan, self.modules_list)
        for m in words("\n".join(values)):
            if reg.plugin_file(m) is not None:
                result.append(m)
            else:
                ma = self.d.plan.module_alias.get(m)
                result.append(ma if ma and reg.plugin_file(ma) is not None else m)
        return result

    def handle_all_depends(self, modref: str, module: str, variant: str, is_aggregated: str) -> None:
        """Dependencies of a module (handle-module with --deps)."""
        dry = self.get("DRY_RUN") == "yes"
        #  In a direct aggregate only the modules of the meta-module are
        #  aggregated, not their dependencies (a recursive aggregate
        #  includes them), as the walker does (scbi.walker)
        if is_aggregated == "direct":
            is_aggregated = "no"
        for dmodule in self.get_all_depends(module, variant, "build-depends"):
            if self.handle_depends(modref, dmodule, "build", is_aggregated) != 0:
                raise Exit(1)
        if not dry:
            self.d.log.line_sep()
        for dmodule in self.get_all_depends(module, variant, "depends"):
            if self.handle_depends(modref, dmodule, "default", is_aggregated) != 0:
                raise Exit(1)
        if not dry:
            self.d.log.line_sep()
        if self.get("DO_TEST") != "no":
            for dmodule in self.get_all_depends(module, variant, "tests-depends"):
                if self.handle_depends(modref, dmodule, "tests", is_aggregated) != 0:
                    raise Exit(1)
            if not dry:
                self.d.log.line_sep()

    # ------------------------------------------------------------ host@

    def host_depends(self, module: str, variant: str) -> list[str]:
        """The host@ dependencies of a module in a cross build."""
        hooks = ["build-depends", "depends"] + (["tests-depends"] if self.get("DO_TEST") != "no" else [])
        return [m for hook in hooks for m in self.get_all_depends(module, variant, hook) if self.is_host_dep(m)]

    def check_host_depends(self, module: str, variant: str) -> None:
        """Without --deps: the host@ dependencies must be built for the host."""
        for modref in self.host_depends(module, variant):
            hmodule, hvariant = (self.d.plan.module_ref(modref, module) + ["", ""])[:2]
            if not os.path.isfile(self.host_dir(hmodule, hvariant, "build-id")):
                self.elog(module, f"{modref}: not built for {self.get('SCBI_HOST')},",
                          f"run scbi {strip_host(modref)} or use --deps")
                raise Exit(1)

    def handle_host_depends(self, modref: str, module: str, variant: str, drefs: Path) -> int:
        """A host@ dependency with --deps in a cross build: the module built
        for the host by a driver run without --target (once per run), its
        build id recorded for the dependent. Returns the status."""
        key = f"{module}/{variant}"
        if key not in self.host_built:
            self.host_built.add(key)
            self.ilog(module, "%BBuilding", f"%t{strip_host(modref)}%c", "for the host",
                      self.get("SCBI_HOST"))
            if self.run_host_build(strip_host(modref)) != 0:
                self.elog(module, "build for the host failed")
                return 1
        bid = Path(self.host_dir(module, variant, "build-id"))
        if bid.is_file():
            with open(drefs, "a") as f:
                f.write(f"{_read_first_line(bid)} {module}\n")
        elif self.get("DRY_RUN") != "yes":
            self.elog(module, f"not built for {self.get('SCBI_HOST')}")
            return 1
        return 0

    def run_host_build(self, modref: str) -> int:
        """``scbi --deps MODREF`` for the host: the options of this run
        that select what is built (plug-ins, build directory, environment,
        plan, jobs, update...), without the target and the ini sections
        (their modules). Its output is the one of this run."""
        import scbi

        d = self.d
        args = [sys.executable, "-m", "scbi", "--deps", "--progress:no",
                f"--plugins={self.get('SCBI_PLUGINS')}", f"--build-dir={self.get('SCBI_BDIR')}",
                f"--jobs={self.get('SCBI_JOBS')}", f"--color:{self.get('DO_COLOR') or 'no'}"]
        if d.cmdline.get("ENV_NAME"):
            args.append(f"--env={d.cmdline['ENV_NAME']}")
        if self.get("SCBI_PLAN"):
            args.append(f"--plan={self.get('SCBI_PLAN')}")
        if self.get("DO_UPDATE") == "yes":
            args.append("--update")
        if self.get("DO_WARNING_EXTERNAL") == "yes":
            args.append("--deps:warning")
        if self.get("DRY_RUN") == "yes":
            args.append("--dry-run")
        args.append(modref)
        env = dict(os.environ)
        pkg = str(Path(scbi.__file__).resolve().parent.parent)
        env["PYTHONPATH"] = pkg + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
        #  a nested run: no ini modules, no stats
        env["SCBI_NESTED"] = "yes"
        #  its steps are part of this run (scbi.steptime)
        env["SCBI_RUN_ID"] = steptime.run_id(d)
        sys.stdout.flush()
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                cwd=os.getcwd(), env=env)
        assert proc.stdout is not None
        #  the blank lines at the end (separator) are the ones of this run
        blanks = 0
        for line in proc.stdout:
            if not line.strip():
                blanks += 1
                continue
            sys.stdout.write("\n" * blanks + line)
            blanks = 0
        sys.stdout.flush()
        return proc.wait()

    def record_dref(self, module: str, variant: str, file: Path) -> None:
        """Port of ``record-dref``."""
        biv = Path(self.get("SCBI_BDIR"), module, f"build-id-{variant}")
        if biv.is_file():
            with open(file, "a") as f:
                f.write(f"{_read_first_line(biv)} {module}\n")

    def module_name(self, modref: str, formodule: str) -> str:
        """Port of ``get-module-name`` (FORMODULE of the caller)."""
        info = (self.d.plan.module_ref(modref, formodule or "@root") + [""] * 4)[:4]
        name = info[0]
        if info[1] != "default":
            name += f"/{info[1]}"
        if info[3] != "NONE":
            name += f":{info[3]}"
        return name

    def handle_depends(self, formodule: str, modref: str, depends_kind: str, is_aggregated: str) -> int:
        """Port of ``handle-depends``; returns the status."""
        d = self.d
        info = d.plan.module_ref(modref, formodule)
        if len(info) > 4:
            self.elog(info[0], *info[4:])
            raise Exit(1)
        module, variant, kind, ref = (info + [""] * 4)[:4]
        is_module = d.registry.plugin_file(module) is not None

        if ref == "skip":
            what = "%BModule" if is_module else "%BDependency"
            self.ilog(module, what, f"%t{module}%c", "marked to be skipped")
            return 0

        finfo = (d.plan.module_ref(formodule) + [""] * 4)[:4]
        fmodule, fvariant = finfo[0], finfo[1]
        drefs = Path(self.get("SCBI_BDIR"), fmodule, f"build-deps-{fvariant}")

        if self.is_host_dep(modref):
            return self.handle_host_depends(modref, module, variant, drefs)

        if kind == "DEV":
            self.handle_module(formodule, modref, depends_kind, is_aggregated)
            self.record_dref(module, variant, drefs)
            return 0

        os.chdir(self.get("SCBI_ROOT"))

        if not is_module:
            if self.check_pkg(fmodule, fvariant, f"{module}:{ref}", quiet=True) == 0:
                return 0
            mname = fmodule if fvariant == "default" else f"{fmodule}/{fvariant}"
            msg = "warning" if self.get("DO_WARNING_EXTERNAL") == "yes" else "error"
            self.out(f"{msg}: missing dependencies for building {mname}")
            for m in reversed(self.modules_list[:-1]):
                self.out(f"{msg}    required by {self.module_name(m, formodule)}")
            hooks = ["build-depends", "depends"] + (["tests-depends"] if self.get("DO_TEST") != "no" else [])
            for hook in hooks:
                for dmodule in self.get_all_depends(fmodule, fvariant, hook):
                    if d.registry.plugin_file(dmodule) is None:
                        self.check_pkg(fmodule, fvariant, dmodule)
            return 0 if self.get("DO_WARNING_EXTERNAL") == "yes" else 1

        self.handle_module(fmodule, modref, depends_kind, is_aggregated)
        self.record_dref(module, variant, drefs)
        return 0

    def sync_dir(self, module: str, variant: str, src: str, dst: str) -> int:
        """``sync-dir SRC DST`` (output to the console)."""
        sys.stdout.flush()
        return generic_steps.Generic(self, "@root", module, variant, "").sync_dir(src, dst)

    def sync_recursive(self, meta: str, variant: str, module: str, tvmdir: str, mdir: str) -> None:
        """``do-sync`` of a recursive aggregate: the installation of
        ``module`` and of its dependencies copied into the meta-module."""
        bdir = self.get("SCBI_BDIR")

        def do_sync(argv: list[str]) -> None:
            a = argv + ["", ""]
            smodule, svariant, _kind, sref = (self.d.plan.module_ref(a[1], a[0]) + [""] * 4)[:4]
            if sref == "skip":
                return
            idir = self.target_dir(smodule, svariant, "install")
            if os.path.isdir(idir):
                self.sync_dir(meta, variant, idir, f"{tvmdir}/.")
            _append_file(Path(bdir, smodule, "source-ref"), Path(mdir, "source-ref"))

        Walker(self).walk("for-all-modules-depends-with-meta", do_sync, module, name="do-sync")

    def check_pkg(self, module: str, variant: str, pkg: str, quiet: bool = False) -> int:
        """``check-pkg PKG`` (its messages to the console unless ``quiet``)."""
        from scbi import ospkg

        sys.stdout.flush()
        return ospkg.OsPackages(self.d).check_pkg(pkg, (lambda line: None) if quiet else self.out)

    def display_ref(self, module: str, variant: str, ref: str) -> str:
        """Port of ``get-module-display-ref``."""
        vcs, _ = vcs_data(self, module, variant)
        vcs_name = vcs[3] if len(vcs) > 3 else ""
        if variant == "native":
            return ref.replace("NONE", "os", 1)
        if not vcs_name:
            return ref.replace("NONE", "n/a", 1)
        if ref == "dev":
            return ref
        default = {"git": "master", "hg": "default", "mercurial": "default",
                   "svn": "trunk", "subversion": "trunk"}.get(vcs_name)
        return ref.replace("NONE", default, 1) if default else ref

    def needed_by(self, module: str, log: str) -> None:
        if len(self.modules_list) > 1:
            self.ilog(module, "needed by:")
            for m in reversed(self.modules_list[:-1]):
                self.ilog(module, f"  ↳ {m}")

    def module_subshell(self, formodule, modref, depends_kind, is_aggregated,
                        module, variant, kind, ref, log, tvdir) -> tuple[int, str]:
        d = self.d
        bdir = self.get("SCBI_BDIR")
        keep = ref.split(":", 1)[0] == "keep"
        if keep:
            steps = self.get("STEPS")
            for s in ("setup", "config", "build", "install", "wrapup"):
                steps = steps.replace(s, "", 1)
            d.set("STEPS", steps)
            for v in ("DO_SETUP", "DO_CONFIG", "DO_BUILD", "DO_INSTALL", "DO_WRAPUP"):
                d.set(v, "no")

        self.ilog(module, "steps:", *words(self.get("STEPS")))

        if keep:
            self.ilog(module, "no update, keep current build")
        else:
            os.chdir(f"{bdir}/{module}")
            lnk = self.get("SCBI_LNK")
            for p in ("src", f"src{lnk}", f"vcs{lnk}"):
                _rm(p)
            rc = sources.handle_sources(self, formodule, modref)
            if rc != 0:
                return 1, "no"

        self.modules_dir = {}
        is_uptodate, msg = "no", ""
        status = self.is_module_up_to_date(modref, formodule, module, variant, ref)
        d.set("SCBI_CHECK_BUILD_CACHE", "no")
        if keep:
            is_uptodate, msg = "yes", "no build needed: keep module"
        elif self.get("DO_TEST") == "yes-only":
            is_uptodate, msg = "yes", ""
        elif status == V_MATCHING:
            is_uptodate, msg = "yes", "no build needed: versions matching"
        elif status == V_NATIVE:
            pass
        elif status == V_NATIVE_MATCHING:
            is_uptodate = "yes"
        elif status in UPTODATE_MESSAGES:
            msg, check = UPTODATE_MESSAGES[status]
            if check:
                d.set("SCBI_CHECK_BUILD_CACHE", "yes")
        else:
            msg = f"unknown status {status}"

        d.set("SCBI_IS_FROM_CACHE", "no")
        cache = self.get("SCBI_CACHE_DIR")
        if cache:
            cbdir = _read_first_line(Path(bdir, module, f"build-id-{variant}"))
            if os.path.isfile(f"{cache}/{cbdir}"):
                if self.get("SCBI_CHECK_BUILD_CACHE") == "yes":
                    cached_dir = _read_first_line(Path(cache, cbdir))
                    if cached_dir != tvdir:
                        bid = _read_first_line(Path(cached_dir, "build-id"))
                        if bid == cbdir:
                            self.sync_dir(module, variant, cached_dir, f"{bdir}/{module}")
                            shutil.copy(f"{cached_dir}/source-id", f"{bdir}/{module}")
                            msg = "trigger: copy from cache"
                            d.set("SCBI_IS_FROM_CACHE", "yes")
                            d.registry.functions[f"{module}-cached"] = Commands("true")
                        else:
                            Path(cache, cbdir).unlink(missing_ok=True)
            elif cbdir:
                Path(cache, cbdir).write_text(tvdir + "\n")

        envtmp = Path(tempfile.mkstemp(dir="/dev/shm" if os.path.isdir("/dev/shm") else None)[1])
        if is_uptodate == "no" or self.get("DO_TEST") != "no":
            d.set("SCBI_ENV_MODULE", str(envtmp))
            #  an exit (e.g. recursive dependencies) ends the module sub-shell
            env_rc = self.module_environment(module, variant, [
                ("handle-build-depends-env", formodule, modref),
                ("handle-env", formodule, modref),
                ("module-env", formodule, modref, "build-env", "record")])
            d.sv.values.pop("SCBI_ENV_MODULE", None)
            if env_rc != 0:
                envtmp.unlink(missing_ok=True)
                return env_rc, is_uptodate

        #  the build link points to the variant
        os.chdir(f"{bdir}/{module}") if os.path.isdir(f"{bdir}/{module}") else None
        lnk = self.get("SCBI_LNK")
        if os.path.isdir("build") and not os.path.islink("build"):
            shutil.rmtree("build")
        elif os.path.islink("build"):
            os.unlink("build")
        elif os.path.isfile(f"build{lnk}") and lnk:
            os.unlink(f"build{lnk}")
        os.symlink(os.path.relpath(os.path.realpath(tvdir), os.getcwd()), "build")

        if is_uptodate == "yes":
            if msg:
                self.ilog(module, *msg.split(" "))
            d.set("STEPS", "tests" if self.get("DO_TEST") != "no" else "")
        else:
            #  The sandbox is about to change: the build id of the previous
            #  build is removed first, the generic install writes the new
            #  one when the build completes. An interrupted or failed build
            #  is then redone at the next run, even with the same build id.
            Path(tvdir, "build-id").unlink(missing_ok=True)
            if msg:
                self.ilog(module, *msg.split(" "))
            if status == B_NOT_UPTODATE and Path(tvdir, "build-deps").is_file():
                self.triggered_by(module, Path(bdir, module, f"build-deps-{variant}"),
                                  Path(tvdir, "build-deps"))
            self.record_build_plan(module, variant)
            self.record_module_env(module, variant)
            self.write_env_cmd(module, variant, envtmp)
            if self.get("DO_INSTALL") != "no" and self.get("SCBI_IS_FROM_CACHE") == "no":
                shutil.rmtree(f"{tvdir}/install", ignore_errors=True)
                Path(bdir, module, "install-id").unlink(missing_ok=True)
                Path(bdir, module, f"install-{self.get('SCBI_TARGET')}-id").unlink(missing_ok=True)
            if (self.get("SAFE_MODE") == "yes" and self.get("SCBI_ISOOT") == "true"
                    and self.get("DO_BUILD") == "yes"):
                _rm(f"{tvdir}/build{lnk}")
        envtmp.unlink(missing_ok=True)

        def generic(step: str) -> int:
            if step not in generic_steps.STEPS:
                return 0
            sys.stdout.flush()
            #  appended to the report log of the module (never truncated)
            return generic_steps.Generic(self, formodule, module, variant, tvdir).step(
                step, self.get("log"), append=True)

        def wrapper(step: str) -> int:
            #  module-variant-wrapper does nothing without a hook or for a
            #  nop hook ({ true }): no shell needed then
            fct = get_hook(d.registry, module, variant, step, d.runner().cross)
            if not fct or step_wrapper.is_nop(d.registry.functions.get(fct)):
                return 0
            #  --build-target=<target>: the build-<target> hook
            tfct, hook = step_wrapper.build_target_hook(d, module, variant, fct)
            if hook and not tfct:
                self.elog(module, "build", "failed:", "no", hook, "hook")
                return 1
            fct = tfct or fct
            return step_wrapper.StepWrapper(self, module, variant).internal(f"{tvdir}/install", fct)

        def run_step(step: str) -> int:
            """The pre-, hook and post- parts of a step: its status."""
            if step == "tests":
                if self.module_environment(module, variant, [
                        ("handle-tests-depends-env", formodule, modref),
                        ("module-env", formodule, modref, "tests-env"),
                        ("module-env", formodule, modref, "env")], hook="tests") != 0:
                    return 1
            res = generic(f"pre-{step}")
            if res != 0:
                self.elog(module, "generic", "module", f"pre-{step}", "failed", "with", "error", str(res))
                return res
            if wrapper(f"pre-{step}") != 0 or wrapper(step) != 0:
                return 1
            res = generic(step)
            if res != 0:
                self.elog(module, "generic", "module", step, "failed", "with", "error", str(res))
                return res
            if wrapper(f"post-{step}") != 0:
                return 1
            res = generic(f"post-{step}")
            if res != 0:
                self.elog(module, "generic", "module", f"post-{step}", "failed", "with", "error", str(res))
            return res

        for step in words(self.get("STEPS")):
            begin = steptime.start()
            res = run_step(step)
            steptime.record(d, module, variant, step, begin, res)
            if res != 0:
                return res, is_uptodate

        if (self.get("DO_CHECK_DEPS") in ("yes", "error") and is_uptodate == "no"
                and self.get("DO_BUILD") != "no" and not keep):
            from scbi import depcheck

            if depcheck.check(self, formodule, modref, module, tvdir) != 0:
                return 1, is_uptodate

        final = self.d.envfile.hook("module_final_step")
        if final is not None:
            self.ilog(module, "final", "step", "starting")
            self.final_step(final, FinalStep(self, f"{tvdir}/install", self.get("SCBI_TARGET"), variant, module,
                                             formodule, modref, depends_kind, "no", is_aggregated, is_uptodate))
            self.ilog(module, "final", "step", "completed")
        return 0, is_uptodate


def _append_file(src: Path, dst: Path) -> None:
    """cat SRC >> DST (an error message when SRC is missing, as cat)."""
    try:
        data = src.read_bytes()
    except OSError:
        sys.stderr.write(f"cat: {src}: No such file or directory\n")
        return
    with open(dst, "ab") as f:
        f.write(data)


def _rm(path: str) -> None:
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
