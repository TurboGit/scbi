"""Handling of a module: sources, up-to-date check, environment, steps,
global install (port of handle-module and its helpers from the scbi
driver).

The flow, the decisions, the messages and the logs are in Python. Some
leaf parts still run as reference Bash code in a hook shell (functions of
hooks/compat.sh and of the runtime): the sources (handle-sources), the
running of a step with its logs (module-wrapper), the environment of the
module and its dependencies (handle-env...), the generic steps of the
runtime (module-setup, module-install...).
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

from scbi.bashcompat import assoc_keys, words
from scbi.bashenv import ShellVars, quote
from scbi.env import Environment
from scbi.errors import Exit, NotImplementedYet
from scbi.hooks.context import HookContext
from scbi.hooks.exec import HookShell, env_code, is_nop, run_code
from scbi.hooks.policy import is_reference
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
        self.modules_dir: dict[str, str] = {}
        self.flatdir: dict[str, str] = {}
        self.ftdir = 1

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

    def shell(self) -> HookShell:
        reg = self.d.registry
        return HookShell(self.d.runtime, reg.functions, self.d.base_env(), loaded=reg.scbi_loaded(), sources=reg.legacy_sources())

    def bash(self, module: str, variant: str, code: str, hook: str = "config",
             arrays: list[str] = ()) -> int:
        """Run driver code in a shell (output to the console), the changes
        to the shell variables are kept."""
        sys.stdout.flush()
        ctx = self.ctx(module, variant, hook)
        rc, arr = env_code(self.shell(), ctx, code, ["SCBI_MODULES_DIR", *arrays], self.out)
        self.d.sv = ctx.env.vars
        if "SCBI_MODULES_DIR" in arr:
            self.modules_dir = arr["SCBI_MODULES_DIR"]
        return rc

    def run(self, module: str, variant: str, code: str, hook: str = "config") -> int:
        """Run driver code in a shell (output to the console); it cannot
        change the driver variables (e.g. code run in a sub-shell in Bash)."""
        sys.stdout.flush()
        return run_code(self.shell(), self.ctx(module, variant, hook), code, self.out).returncode

    def capture(self, module: str, variant: str, code: str) -> str:
        """``$(code)``: output of driver code, trailing newlines removed."""
        ctx = self.ctx(module, variant)
        lines: list[str] = []
        run_code(self.shell(), ctx, code + " 2>/dev/null", lines.append)
        return "\n".join(lines).rstrip("\n")

    def final_step(self, hook, ctx) -> None:
        """``module_final_step(ctx)`` of the Python environment file (an
        error in it is reported, the build goes on as with Bash)."""
        sys.stdout.flush()
        try:
            hook(ctx)
        except Exception as e:  # noqa: BLE001 - the user's code
            self.elog(ctx.module, "module_final_step:", f"{type(e).__name__}:", str(e))
        sys.stdout.flush()

    def capture_raw(self, module: str, variant: str, code: str) -> str:
        """The standard output of driver code, as is."""
        from scbi.hooks.exec import run_code

        lines: list[str] = []
        run_code(self.shell(), self.ctx(module, variant), code, lines.append)
        return "\n".join(lines)

    def module_env(self, module: str, variant: str, code: str) -> ShellVars:
        """The driver variables after running ``code`` (e.g. the
        environment setup of a module) on a copy: the driver is not
        changed (a sub-shell in Bash)."""
        sv = self.d.sv
        copy_sv = ShellVars(dict(sv.values), set(sv.exported), dict(sv.functions))
        ctx = self.ctx(module, variant)
        ctx.env = Environment(copy_sv)
        lines: list[str] = []
        env_code(self.shell(), ctx, code + " 2>/dev/null", ["SCBI_MODULES_DIR"], lines.append)
        return ctx.env.vars

    def ported(self, name: str) -> bool:
        """The Python port of the runtime function ``name`` may be used:
        it is not redefined by the user (scbi.hooks.policy)."""
        d = self.d
        return is_reference(name, d.runtime.functions, d.sv.functions, d.registry.functions)

    def bash_words(self, module: str, variant: str, call: str) -> tuple[list[str], int]:
        """``r=( $(call) )``: the words and the status of a Bash call."""
        lines: list[str] = []
        rc = run_code(self.shell(), self.ctx(module, variant),
                      f'__r=( $({call}) ); __s=$?; echo "${{__r[*]}}"; exit $__s', lines.append).returncode
        return words("\n".join(lines)), rc

    def fn_exists(self, name: str) -> bool:
        d = self.d
        return (name in d.registry.functions or name in d.runtime.functions or name in d.sv.functions
                #  exported in the environment (export -f)
                or f"BASH_FUNC_{name}%%" in d.sv.values)

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
            setup = (f"handle-build-depends-env @root {quote(modref)}\n"
                     f"handle-module-env @root {quote(modref)} env\n"
                     f"handle-module-env @root {quote(modref)} build-env\n")
            try:
                if interp.is_commands(self, fct):
                    sv = self.module_env(module, variant, setup)
                    chunks: list[str] = []
                    interp.Hook(self, module, variant, fct,
                                [self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), variant], tdir, sv).run(
                        chunks.append, err=lambda text: None)
                    mver = "".join(chunks).rstrip("\n")
                else:
                    mver = self.capture(module, variant, (
                        f"{setup}{fct} \"$SCBI_PREFIX\" \"$SCBI_TARGET\" {quote(variant)}"))
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
        osfile = self.get("SCBI_OS_MODULE_FILE")
        if osfile:
            out += ["", "# OS specific support", Path(osfile).read_text().rstrip("\n")]
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
            with open(log, "w") as f:
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

        log = f"{self.get('SCBI_LOGS')}/{self.get('TODAY')}/{self.get('SCBI_TARGET')}-{module}-{variant}-report.log"
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
            self.ilog(module, "%BModule", f"%t{module}%c", "built only if explitly specified")
            return

        self.modules_list.append(module if variant == "default" else f"{module}/{variant}")
        try:
            self._handle_module(formodule, modref, depends_kind, is_aggregated,
                                module, variant, kind, ref, log)
        finally:
            self.modules_list.pop()

    def _handle_module(self, formodule, modref, depends_kind, is_aggregated,
                       module, variant, kind, ref, log) -> None:
        d = self.d
        bdir = self.get("SCBI_BDIR")
        tvdir = self.target_dir(module, variant)
        os.makedirs(f"{tvdir}/logs", exist_ok=True)
        open(log, "w").close()
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

        if self.get("DRY_RUN") == "yes":
            self.out(modref)
            return

        d.log.clog(module)

        purge = self.get("DO_PURGE")
        if purge in ("yes", "only"):
            self.ilog(module, "%BPurging", f"%t{module}%c", "for", f"{self.get('SCBI_TARGET')}/{variant}")
            if os.path.isdir(f"{bdir}/{module}") and generic_steps.python_allowed(self, "purge"):
                sys.stdout.flush()
                generic_steps.Generic(self, formodule, module, variant,
                                      self.target_dir(module, variant)).step("purge", None)
            elif os.path.isdir(f"{bdir}/{module}"):
                self.run(module, variant, (
                    f"module-purge {quote(f'{bdir}/{module}')} {quote(formodule)} {quote(module)} "
                    f"{quote(variant)} \"$SCBI_TARGET\""))

        if self.get("DO_CLEAN_INSTALL") == "yes":
            self.ilog(module, "Clean", module, "install for", f"{self.get('SCBI_TARGET')}/{variant}")
            if os.path.isdir(f"{bdir}/{module}"):
                self.run(module, variant, (
                    f"module-clean-install {quote(f'{tvdir}/install')} {quote(formodule)} "
                    f"{quote(module)} {quote(variant)} \"$SCBI_TARGET\""))
            return

        if purge == "only":
            return

        disp = self.display_ref(module, variant, ref)

        d.log.line_sep()
        self.ilog(module, "%BBuilding", f"%t{module}%c", f"[%g{' '.join(variant.split('.'))}%c]",
                  f"(%g{disp}%c)", tee=log)

        start = time.monotonic()

        if formodule != "@root":
            self.needed_by(module, log)

        if self.get("SCBI_HOST") == self.get("SCBI_TARGET"):
            self.ilog(module, "native", self.get("SCBI_TARGET"), tee=log)
        else:
            self.ilog(module, "cross", self.get("SCBI_TARGET"), tee=log)

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
            self.ilog(module, "timing:", time.strftime("%H:%M:%S", time.gmtime(secs)), tee=log)

        self.ilog(module, "End", "Building", module, f"[{' '.join(variant.split('.'))}]", f"({disp})", tee=log)
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
            #  $IS_AGGREDATED (sic) is always empty
            amode = agg_mode if agg_mode != "no" else ""
            for dmodule in self.get_all_depends(meta, variant, "build-depends"):
                if self.handle_depends(meta, dmodule, "build", amode) != 0:
                    return 1

        start = time.monotonic()
        d.log.line_sep()
        self.ilog(meta, "%BMetamodule", f"%t{meta}%c", f"[%g{vdisp}%c]", "setup", tee=log)
        if formodule != "@root":
            self.needed_by(formodule, log)

        def internal_wrapper(fct: str) -> int:
            if not fct:
                return 0
            if step_wrapper.python_allowed(self):
                return step_wrapper.StepWrapper(self, meta, variant).internal(f"{bdir}/install", fct)
            return self.run(meta, variant, (
                f"_internal_module-variant-wrapper {quote(f'{bdir}/install')} {quote(meta)} "
                f"{quote(variant)} {quote(fct)}"))

        if internal_wrapper(fct_setup) != 0:
            return 1
        self.ilog(meta, "End", "metamodule", meta, f"[{vdisp}]", "setup", tee=log)
        d.log.line_sep()

        do_agg_prefix = False
        tvmdir = ""
        #  $module: local of handle-module, assigned by the loop below
        leaked = meta
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
                leaked = m
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
                            self.run(meta, variant, _DO_SYNC.format(
                                tvmdir=quote(tvmdir), mdir=quote(mdir), module=quote(m)))
                        else:
                            self.run(meta, variant, f"sync-dir {quote(idir)} {quote(f'{tvmdir}/.')}")
                    _append_file(Path(bdir, m, "source-ref"), Path(mdir, "source-ref"))
            do_agg_prefix = True

        is_utd = "no"
        tvdir = self.target_dir(meta, variant)
        os.chdir(mdir)
        Path(f"build-id-{variant}").write_text(
            build_id(self, self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"), formodule, meta, variant))
        if _same(Path(f"build-id-{variant}"), Path(tvdir, "build-id")) and self.get("DO_FORCE") == "no":
            is_utd = "yes"
        shutil.copy(f"build-id-{variant}", f"{tvdir}/build-id")

        d.log.line_sep()
        self.ilog(meta, "%BMetamodule", f"%t{meta}%c", f"[%g{vdisp}%c]", "wrapup", tee=log)
        if formodule != "@root":
            self.needed_by(formodule, log)

        if is_utd == "no":
            if self.get("DO_FORCE") == "yes":
                self.ilog(leaked, "trigger: forced")
            elif Path(tvdir, "build-deps").is_file():
                self.ilog(leaked, "trigger: build not up-to-date")
                self.triggered_by(leaked, Path(f"build-deps-{variant}"), Path(tvdir, "build-deps"))
            elif Path(f"build-deps-{variant}").is_file():
                self.ilog(leaked, "trigger: not yet built")
            if internal_wrapper(fct_wrapup) != 0:
                return 1

        if Path(f"build-deps-{variant}").is_file():
            shutil.copy(f"build-deps-{variant}", f"{tvdir}/build-deps")

        if agg_mode != "no" and do_agg_prefix:
            ok, idir = self.handle_prefix(meta, variant, ref, log)

        final = self.d.envfile.hook("module_final_step")
        if final is not None:
            mmode = "aggregate" if agg_mode != "no" else "yes"
            self.ilog(meta, "final", "step", "starting", tee=log)
            self.final_step(final, FinalStep(self, f"{tvmdir}/install", self.get("SCBI_TARGET"), variant, meta,
                                             formodule, meta, depends_kind, mmode, is_aggregated, is_utd))
            self.ilog(meta, "final", "step", "completed", tee=log)
        elif self.fn_exists("module-final-step"):
            mmode = "aggregate" if agg_mode != "no" else "yes"
            self.ilog(meta, "final", "step", "starting", tee=log)
            self.run(meta, variant, (
                f"module-final-step {quote(f'{tvmdir}/install')} \"$SCBI_TARGET\" {quote(variant)} "
                f"{quote(meta)} {quote(depends_kind)} {mmode} {quote(is_aggregated)} {is_utd}"))
            self.ilog(meta, "final", "step", "completed", tee=log)

        secs = int(time.monotonic() - start)
        if secs >= 5:
            self.ilog(meta, "timing:", time.strftime("%H:%M:%S", time.gmtime(secs)), tee=log)
        self.ilog(meta, "End", "metamodule", meta, f"[{vdisp}]", "wrapup", tee=log)
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

        if kind == "DEV":
            self.handle_module(formodule, modref, depends_kind, is_aggregated)
            self.record_dref(module, variant, drefs)
            return 0

        os.chdir(self.get("SCBI_ROOT"))

        if not is_module:
            if self.run(fmodule, fvariant, f"check-pkg {quote(f'{module}:{ref}')} > /dev/null") == 0:
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
                        self.run(fmodule, fvariant, f"check-pkg {quote(dmodule)}")
            return 0 if self.get("DO_WARNING_EXTERNAL") == "yes" else 1

        self.handle_module(fmodule, modref, depends_kind, is_aggregated)
        self.record_dref(module, variant, drefs)
        return 0

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
            self.ilog(module, "needed by:", tee=log)
            for m in reversed(self.modules_list[:-1]):
                self.ilog(module, f"  ↳ {m}", tee=log)

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

        self.ilog(module, "steps:", *words(self.get("STEPS")), tee=log)

        if keep:
            self.ilog(module, "no update, keep current build")
        else:
            os.chdir(f"{bdir}/{module}")
            lnk = self.get("SCBI_LNK")
            for p in ("src", f"src{lnk}", f"vcs{lnk}"):
                _rm(p)
            if sources.python_allowed(self):
                rc = sources.handle_sources(self, formodule, modref)
            else:
                rc = self.bash(module, variant, f"handle-sources {quote(formodule)} {quote(modref)}")
            if rc != 0:
                return 1, "no"

        if self.get("SCBI_HOST") != self.get("SCBI_TARGET"):
            Environment(d.sv).target_env(f"{bdir}/install", self.get("SCBI_TARGET"),
                                         self.get("SCBI_HOST"), bdir)

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
                            self.run(module, variant, f"sync-dir {quote(cached_dir)} {quote(f'{bdir}/{module}')}")
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
            env_rc = self.bash(module, variant, (
                f"handle-build-depends-env {quote(formodule)} {quote(modref)}\n"
                f"handle-env {quote(formodule)} {quote(modref)}\n"
                f"handle-module-env {quote(formodule)} {quote(modref)} build-env >> $SCBI_ENV_MODULE\n"
                "unset SCBI_ENV_MODULE"))
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
                Path(tvdir, "build-id").unlink(missing_ok=True)
        envtmp.unlink(missing_ok=True)

        teeopt = "" if self.get("SCBI_DLOG") == "yes" else "-a"
        args = (f"{quote(f'{tvdir}/install')} {quote(formodule)} {quote(module)} "
                f"{quote(variant)} \"$SCBI_TARGET\" \"$SCBI_ISOOT\"")

        def generic(step: str) -> int:
            if not self.fn_exists(f"module-{step}"):
                return 0
            if generic_steps.python_allowed(self, step):
                sys.stdout.flush()
                return generic_steps.Generic(self, formodule, module, variant, tvdir).step(
                    step, self.get("log"), append=bool(teeopt))
            return self.run(module, variant, (
                f"cd {quote(f'{bdir}/{module}')}\n"
                f"module-{step} {args} 2>&1 | tee {teeopt} \"$log\"\n"
                "exit ${PIPESTATUS[0]}"))

        def wrapper(step: str) -> int:
            #  module-variant-wrapper does nothing without a hook or for a
            #  nop hook ({ true }): no shell needed then
            fct = get_hook(d.registry, module, variant, step, d.runner().cross)
            if not fct or is_nop(d.registry.functions.get(fct)):
                return 0
            if step_wrapper.python_allowed(self):
                return step_wrapper.StepWrapper(self, module, variant).internal(f"{tvdir}/install", fct)
            return self.run(module, variant, (
                f"module-variant-wrapper {quote(f'{tvdir}/install')} {quote(module)} "
                f"{quote(variant)} {quote(step)}"))

        for step in words(self.get("STEPS")):
            if step == "tests":
                if self.bash(module, variant, (
                    f"handle-tests-depends-env {quote(formodule)} {quote(modref)}\n"
                    f"handle-module-env {quote(formodule)} {quote(modref)} tests-env\n"
                    f"handle-module-env {quote(formodule)} {quote(modref)} env"), hook="tests") != 0:
                    return 1, is_uptodate
            res = generic(f"pre-{step}")
            if res != 0:
                self.elog(module, "generic", "module", f"pre-{step}", "failed", "with", "error", str(res))
                return res, is_uptodate
            if wrapper(f"pre-{step}") != 0 or wrapper(step) != 0:
                return 1, is_uptodate
            res = generic(step)
            if res != 0:
                self.elog(module, "generic", "module", step, "failed", "with", "error", str(res))
                return res, is_uptodate
            if wrapper(f"post-{step}") != 0:
                return 1, is_uptodate
            res = generic(f"post-{step}")
            if res != 0:
                self.elog(module, "generic", "module", f"post-{step}", "failed", "with", "error", str(res))
                return res, is_uptodate

        final = self.d.envfile.hook("module_final_step")
        if final is not None:
            self.ilog(module, "final", "step", "starting", tee=log)
            self.final_step(final, FinalStep(self, f"{tvdir}/install", self.get("SCBI_TARGET"), variant, module,
                                             formodule, modref, depends_kind, "no", is_aggregated, is_uptodate))
            self.ilog(module, "final", "step", "completed", tee=log)
        elif self.fn_exists("module-final-step"):
            self.ilog(module, "final", "step", "starting", tee=log)
            for name, value in (("FORMODULE", formodule), ("MODREF", modref), ("module", module),
                                ("variant", variant)):
                d.set(name, value)
            self.bash(module, variant, (
                f"module-final-step {quote(f'{tvdir}/install')} \"$SCBI_TARGET\" {quote(variant)} "
                f"{quote(module)} {quote(depends_kind)} no {quote(is_aggregated)} {quote(is_uptodate)}"))
            self.ilog(module, "final", "step", "completed", tee=log)
        return 0, is_uptodate


#  do-sync of handle-meta-module (recursive aggregate)
_DO_SYNC = r"""
TVMDIR={tvmdir}
MDIR={mdir}
function do-sync()
{{
    local FORMODULE=$1
    local MODREF=$2
    local smodule_info=()
    get-module-ref smodule_info $MODREF $FORMODULE
    local module=${{smodule_info[0]}}
    local variant=${{smodule_info[1]}}
    local ref=${{smodule_info[3]}}
    [[ "$ref" == "skip" ]] && return
    local IDIR=""
    get-target-dir IDIR $module $variant install
    [[ -d $IDIR ]] && sync-dir $IDIR $TVMDIR/.
    cat $SCBI_BDIR/$module/source-ref >> $MDIR/source-ref
}}
for-all-modules-depends-with-meta do-sync {module}
"""


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
