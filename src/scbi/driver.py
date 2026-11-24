"""The scbi driver: command line, setup, plan, then module handling.

Port of the main code of the Bash driver (scbi): global settings,
ini-apply-values, the two command line passes, sub-command detection,
setup-generic-tool-env (colors, plug-ins directory, environment file,
runtime, version, plan cache and loading, usage, statistics, module
references of the command line, plan rewriting).

The driver state is kept, as in Bash, in variables (``self.sv``): ini
files and environment files may set any of them, the exported ones are
given to the hooks.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scbi import env as env_mod
from scbi import envyaml
from scbi.bashcompat import assoc_keys, read_fields, read_lines, words
from scbi.bashenv import ShellVars
from scbi.discriminants import forced_discriminants, probe_host, setup_discriminants
from scbi.errors import Exit, NotImplementedYet
from scbi.ini import IniDB, expand_value
from scbi.log import Logger
from scbi.modref import parse_module_ref
from scbi.plugin import formats
from scbi.plan import PlanError, PlanLoader, PlanState

#  Replaced by the installation (as in the Bash driver)
SCBI_VERSION = "@VERSION@"

OS_NAMES = ("deb", "ubt", "cos", "rhl", "fed", "win", "mingw")


USAGE_OPTIONS = """
   modulen  <name>           build from repository main branch
   modulen  <name>/<variant> build <variant> from repository version
   modulen  <name>:<branch>  build from repository version <branch>
   modulen  <name>:#<ver>    build from tarball version <ver>
   modulen  <name>:dev       build from user's repository current branch

   -h | --help              this help message
   -v | --version           display driver & plug-ins versions
   -q | --quiet             do not display information log
      | --color:[n]         use colored output (no, dark, light)
      | --ini=<section>     load ini file given section
      | --prefix=<dir>      the global install directory
      | --build-dir=<dir>   the root build directory.
      | --flat              use a flatter directory structure
   -e | --env=<name>        environment file .env-<name>.yaml
      | --plan=<name>       a build plan for modules
      | --enable-<name>     enable feature name
   -t | --target=<name>     the target to build for ({target})
      | --plugins=<dir>     specify the modules/plugins directory
   -j | --jobs=<n>          max compilation jobs, set $SCBI_JOBS
   -S | --no-setup          skip setup
   -I | --no-install        skip install
   -W | --no-wrapup         skip wrapup
   -u | --update            do update
      | --update:prefetch   do update, the sources fetched ahead in parallel
   -s | --setup             do setup
   -c | --config            do config
   -b | --build             do build
        --build-target=<t>  build with the build-<t> hook
   -i | --install           do install
   -w | --wrapup            do wrapup
      | --clean-install     clean installation directory
      | --archive           check for archive only if explicitly specified
      | --tests[:only][=O]  run the testsuite, eventually build
   -d | --deps[:warning]    check/build dependencies
   -a | --create-archive    build binary archive
      | --standalone        create a standalone source archive
   -l | --log:n             log display control yes|no|on-failure
   -f | --force             force rebuild, do not check build id
   -p | --purge[:only]      remove build directory, build eventually
      | --safe              clean-up build directory before configure
      | --dry-run           only list modules handled
      | --stat[:short|full] display some status of current setup
      | --progress[:bar|line|no]  build progress on the terminal (bar)
   -n | --no-patch          do not apply patches
      | --clear-cache       remove cached module's versions"""

#  ini key -> driver variable (ini-apply-values)
INI_KV = {
    "build-dir": "SCBI_BDIR", "env": "ENV_NAME", "git-repo": "SCBI_GIT_REPO",
    "hg-repo": "SCBI_HG_REPO", "jobs": "SCBI_JOBS", "log": "SCBI_LOGS",
    "patch": "SCBI_PATCH", "plan": "SCBI_PLAN", "plugins": "SCBI_PLUGINS",
    "prefix": "SCBI_PREFIX", "root-dir": "SCBI_ROOT", "svn-repo": "SCBI_SVN_REPO",
    "archives": "SCBI_ARCHIVES", "target": "SCBI_TARGET",
}

INI_SKIP = (",setup,config,build,install,wrapup,force,modules,stat,"
            "update,purge,archive,deps,safe,tar,no-patch,enable,run,")

GETOPT_SHORT = "j:adefSIuscbilnpqvwWh"
GETOPT_LONG = [
    "no-setup,no-install,update,update:prefetch,setup,config",
    "build,build-target:,install,clean-install,create-archive",
    "log,log:yes,log:no,log:on-failure,purge,purge:only",
    "prefix:,deps,deps:warning,archive,force,env:,no-patch",
    "no-wrapup,wrapup,safe,standalone",
    "dry-run,jobs:,list-plan:",
    "progress,progress:bar,progress:line,progress:no",
]


def md5_echo(text: str) -> str:
    """get-string-md5: md5sum of ``echo $text`` (unquoted)."""
    return hashlib.md5((" ".join(words(text)) + "\n").encode()).hexdigest()


def is_plugins_dir(path: str) -> bool:
    """A directory holding plug-in definitions."""
    return os.path.isdir(path) and any(formats.format_of(p) for p in Path(path).iterdir())


class Driver:
    def __init__(self, argv0: str, environ: dict[str, str] | None = None):
        self.argv0 = argv0
        self.environ = dict(os.environ if environ is None else environ)
        #  shell variables of the driver; the process environment is the
        #  initial set of exported variables
        self.sv = ShellVars(dict(self.environ), set(self.environ))
        self.cmdline: dict[str, str] = {}
        self.scbiopts: list[str] = []
        self.modules: list[str] = []
        self.ini = IniDB()
        self.ini_modules: list[str] = []
        self.ini_options: list[str] = []
        self.ini_subcmd = ""
        #  the modules of the build (planned_modules)
        self._planned: list[tuple[str, str, str, str, str]] | None = None
        #  the YAML environment file (settings and functions)
        self.envfile = envyaml.EnvFile()
        self.plan = PlanState()
        self.discriminants: list[str] = []
        self.log: Logger | None = None
        self.testsuite = self.environ.get("SCBI_TESTSUITE") == "yes"
        self._registry = None
        self._runner = None

    # ------------------------------------------------------------ helpers

    def get(self, name: str) -> str:
        return self.sv.values.get(name, "")

    def set(self, name: str, value: str, export: bool | None = None) -> None:
        self.sv.values[name] = value
        if export:
            self.sv.exported.add(name)

    def echo(self, *text: str) -> None:
        sys.stdout.write(" ".join(text) + "\n")
        sys.stdout.flush()

    def base_env(self) -> dict[str, str]:
        return self.sv.environ()

    def which(self, prog: str) -> str | None:
        return shutil.which(prog, path=self.get("PATH"))

    # ------------------------------------------------------------- globals

    def init_globals(self) -> None:
        """Top-level settings of the Bash driver, before the body."""
        s = self.set
        s("CDPATH", "")
        s("SCBI_VERSION", SCBI_VERSION, export=True)
        s("SCBI_BINARY", os.path.realpath(self.argv0), export=True)
        s("SCBI_IS_WINDOWS", "no", export=True)
        s("SCBI_OS_MODULE", "")
        missing = [t for t in ("rsync", "sed", "diff") if not self.which(t)]
        uname = " ".join(os.uname())
        if re.search("Cygwin", uname):
            s("SCBI_IS_WINDOWS", "yes", export=True)
            s("SCBI_HOST", "x86_64-cygwin", export=True)
            s("SCBI_OS_MODULE", "windows")
        elif re.search("Msys", uname):
            s("SCBI_IS_WINDOWS", "yes", export=True)
            s("SCBI_HOST", "x86_64-mingw64", export=True)
            s("SCBI_OS_MODULE", "windows")
        else:
            if not self.which("gcc"):
                missing.append("gcc")
            else:
                host = subprocess.run(["gcc", "-dumpmachine"], capture_output=True, text=True).stdout.strip()
                host = host.replace("-pc", "", 1).replace("-unknown", "", 1)
                s("SCBI_HOST", host, export=True)
        if missing:
            self.echo(f"Required tools {' '.join(missing)} missing, please install")
            raise Exit(1)
        #  Testsuite only: the OS runtime module can be forced (test114,
        #  the Bash driver is patched with sed for the same purpose)
        if self.testsuite and self.environ.get("SCBI_OS_MODULE"):
            s("SCBI_OS_MODULE", self.environ["SCBI_OS_MODULE"])
        s("SCBI_TARGET", self.get("SCBI_HOST"), export=True)
        s("SCBI_TARGET_SPECIFIED", "no")
        s("SCBI_ENV_DIR", "", export=True)
        default_env = self.get("SCBI_DEFAULT_ENV")
        s("ENV_NAME", f"-{default_env}" if default_env else "")
        s("SCBI_DLOG", "on-failure")
        s("SCBI_PLUGINS", f"{os.getcwd()}/scripts.d", export=True)
        if not self.get("SCBI_JOBS"):
            s("SCBI_JOBS", str(os.cpu_count() or 1), export=True)
        if not self.get("SCBI_HALF_JOBS"):
            s("SCBI_HALF_JOBS", str(int(self.get("SCBI_JOBS") or "1") // 2), export=True)
        s("SCBI_HANDLED", tempfile.mkstemp(dir="/dev/shm" if os.path.isdir("/dev/shm") else None)[1])
        s("SCBI_CURRENT_MODULE", "", export=True)
        s("SCBI_CHECK_BUILD_CACHE", "no")
        if self.get("SCBI_CACHE_DIR") == "no":
            s("SCBI_CACHE_DIR", "")
        else:
            cache = self.get("SCBI_CACHE_DIR") or f"{self.get('HOME')}/.cache/scbi"
            s("SCBI_CACHE_DIR", cache)
            os.makedirs(cache, exist_ok=True)
        for name, value in {
            "DO_PURGE": "no", "SCBI_PREFIX": "", "SCBI_DEFAULT_PREFIX": "yes", "DO_QUIET": "no",
            "DO_UPDATE": "no", "DO_PREFETCH": "no", "DO_ARCHIVE": "no", "DO_FORCE": "no", "DO_STAT": "no",
            "DO_FLAT": "no", "DO_DEPS": "no", "DO_CLEAN_INSTALL": "no", "DO_PLAN": "no",
            "DO_SUBCMD": "no", "DO_CLEAR_CACHE": "no", "DEPS": "no", "SCBI_ISOOT": "true",
            "DO_PATCH": "yes", "STEPS": "", "BUILD_SCBI_TARGET": "", "SCBI_PLAN": "",
            "ARCHIVE_CACHE": "yes", "DRY_RUN": "no", "SAFE_MODE": "no", "SCBI_LNK": "",
            "DO_STANDALONE": "no", "DO_HELP": "no", "DO_VERSION": "no", "DO_SHELL": "no",
            "DO_RUN": "no", "DO_RUN_CMD": "", "DO_WARNING_EXTERNAL": "no",
            "SCBI_TESTS_OPTIONS": "", "DO_COLOR": "no", "SCBI_CBOLD": "", "SCBI_CTEXT": "",
            "SCBI_CCLEAR": "", "SCBI_CRED": "", "SCBI_CGREEN": "", "SCBI_CBLUE": "",
            "DO_SETUP": "yes", "DO_CONFIG": "yes", "DO_BUILD": "yes", "DO_INSTALL": "yes",
            "DO_TEST": "no", "DO_WRAPUP": "yes",
        }.items():
            s(name, value)
        for name in ("SCBI_ROOT", "SCBI_BDIR", "SCBI_CLANG_VERSION", "SCBI_GTK_VERSION",
                     "SCBI_PLAN", "SCBI_OS_NAME", "SCBI_OS_VERSION", "SCBI_ISOOT",
                     "SCBI_MODULES_LIST", "SCBI_CBOLD", "SCBI_CRED", "SCBI_CGREEN",
                     "SCBI_CBLUE", "SCBI_CCLEAR", "SCBI_CTEXT"):
            self.sv.exported.add(name)
            self.sv.values.setdefault(name, "")

    def do_clear_steps(self) -> None:
        for v in ("DO_SETUP", "DO_CONFIG", "DO_BUILD", "DO_INSTALL", "DO_WRAPUP"):
            if self.get(v) == "yes":
                self.set(v, "no")

    # ------------------------------------------------------------------ ini

    def ini_get(self, section: str, var: str) -> str:
        return self.ini.get_option(section, var, self.sv, self.base_env())

    def ini_apply_values(self, section: str) -> None:
        """Port of ``ini-apply-values``."""
        for k in assoc_keys(self.ini.db):
            m = re.fullmatch(r"([^.]+)\.([^.]+)", k)
            sec, var = (m.group(1), m.group(2)) if m else ("", k)
            if not ((not sec and not section) or (sec == "common" and section) or section == sec):
                continue
            if var in INI_KV:
                var = INI_KV[var]
                val = self.ini_get(section, k)
                if not self.cmdline.get(var):
                    self.cmdline[var] = val
                if var == "SCBI_PREFIX":
                    self.set("SCBI_DEFAULT_PREFIX", "no")
            else:
                var = var.replace("-", "_")
                val = expand_value(self.ini.db[k], self.sv.values.get)
            if val and f",{var}," not in INI_SKIP:
                self.set(var, val, export=True)

        feat = self.ini_get(section, "enable")
        if feat:
            for f in words(feat.replace(",", " ")):
                self.set(f"SCBI_{f.replace('-', '_')}_SET", "true", export=True)

        self.ini_modules = words(self.ini_get(section, "modules"))

        for opt in ("setup", "config", "build", "install", "wrapup", "color",
                    "quiet", "force", "update", "purge", "archive", "stat"):
            o = self.ini_get(section, opt)
            if opt == "update" and o == "prefetch":
                #  update = prefetch: --update:prefetch
                self.set("DO_PREFETCH", "yes", export=True)
                o = "yes"
            if o:
                self.set(f"DO_{opt.upper()}", o, export=True)

        for opt in ("safe", "tar", "no-patch", "clear-cache"):
            if self.ini_get(section, opt).upper() == "YES":
                self.ini_options.append(f"--{opt}")

        o = self.ini_get(section, "deps")
        if o:
            self.set("DEPS", o)
        o = self.ini_get(section, "run")
        if o:
            self.set("DO_RUN", "yes")
            self.set("DO_RUN_CMD", o)
            self.ini_subcmd = "shell"
        o = self.ini_get(section, "tests")
        if o:
            self.set("DO_TEST", "yes")
            if o == "only":
                self.do_clear_steps()
                self.set("DO_TEST", "yes-only")
        o = self.ini_get(section, "tests-list")
        if o:
            self.set("SCBI_TESTS_OPTIONS", o)
        self.ini_options += words(self.ini_get(section, "options"))

    def ini_load_files(self) -> None:
        home = None if self.testsuite else Path(self.get("HOME") or "/")
        self.ini.load_files(home, Path("."), self.get("SCBI_INI_FILE"))

    # --------------------------------------------------------- first pass

    def first_pass(self, args: list[str]) -> None:
        c = self.cmdline
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-h", "--help"):
                c["DO_HELP"] = "yes"
                break
            if a in ("-v", "--version"):
                c["DO_VERSION"] = "yes"
                break
            if a in ("-f", "--force"):
                c["DO_FORCE"] = "yes"
            elif a == "--clear-cache":
                c["DO_CLEAR_CACHE"] = "yes"
            elif a in ("-q", "--quiet"):
                c["DO_QUIET"] = "yes"
            elif a in ("--color:dark", "--color:light", "--color:no"):
                c["DO_COLOR"] = a.split(":", 1)[1]
            elif a == "-e":
                c["ENV_NAME"] = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            elif a.startswith("--env"):
                c["ENV_NAME"] = a.split("=", 1)[1] if "=" in a else a
            elif a == "-t":
                c["SCBI_TARGET"] = args[i + 1] if i + 1 < len(args) else ""
                i += 1
                c["SCBI_TARGET_SPECIFIED"] = "yes"
            elif a.startswith("--target="):
                c["SCBI_TARGET"] = a.split("=", 1)[1]
                c["SCBI_TARGET_SPECIFIED"] = "yes"
            elif a.startswith("--plan"):
                c["SCBI_PLAN"] = a.split("=", 1)[1] if "=" in a else a
            elif a == "--stat:full":
                c["DO_STAT"] = "full"
            elif a == "--stat:short":
                c["DO_STAT"] = "short"
            elif a == "--stat":
                c["DO_STAT"] = "yes"
            elif a in ("--progress", "--progress:bar"):
                c["SCBI_PROGRESS"] = "bar"
            elif a == "--progress:line":
                c["SCBI_PROGRESS"] = "line"
            elif a == "--progress:no":
                c["SCBI_PROGRESS"] = "no"
            elif a == "--flat":
                c["DO_FLAT"] = "yes"
            elif a.startswith("--build-dir"):
                c["SCBI_BDIR"] = a.split("=", 1)[1] if "=" in a else a
            elif a.startswith("--plugins"):
                val = a.split("=", 1)[1] if "=" in a else a
                c["SCBI_PLUGINS"] = val
                if not is_plugins_dir(val):
                    self.echo(f"{self.argv0}: no plugins found in {val}")
                    raise Exit(1)
            elif a.startswith("--enable-"):
                var = a[len("--enable-"):]
                self.set(f"SCBI_{var.replace('-', '_')}_SET", "true", export=True)
            elif a.startswith("--tests:only"):
                self.do_clear_steps()
                c["DO_TEST"] = "yes-only"
                c["SCBI_TESTS_OPTIONS"] = " ".join(words(a.replace("=", " ", 1))[1:])
            elif a.startswith("--tests"):
                c["DO_TEST"] = "yes"
                c["SCBI_TESTS_OPTIONS"] = " ".join(words(a.replace("=", " ", 1))[1:])
            elif a.startswith("--ini"):
                for section in words(a.split("=", 1)[1] if "=" in a else a) or [""]:
                    self.ini_apply_values(section)
            elif a.startswith("-"):
                self.scbiopts.append(a)
            else:
                self.modules.append(a)
            i += 1

    # -------------------------------------------------------- second pass

    def getopt(self, args: list[str]) -> list[str]:
        """Run util-linux getopt as the Bash driver does (same errors)."""
        cmd = ["getopt", "-u", "-o", GETOPT_SHORT]
        for longs in GETOPT_LONG:
            cmd += ["-l", longs]
        cmd += ["--", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=self.base_env())
        if proc.returncode != 0:
            sys.stdout.write(proc.stderr)
            self.echo('try "scbi --help" for more information.')
            raise Exit(1)
        return words(proc.stdout)

    def second_pass(self) -> None:
        opts = self.getopt(words(" ".join(self.scbiopts + self.ini_options + self.modules)))
        self.modules = []
        i = 0
        s = self.set
        while i < len(opts):
            a = opts[i]
            nxt = opts[i + 1] if i + 1 < len(opts) else ""
            if a in ("-a", "--create-archive"):
                s("DO_ARCHIVE", "yes")
            elif a == "--archive":
                s("ARCHIVE_CACHE", "no")
            elif a in ("-S", "--no-setup"):
                s("DO_SETUP", "no")
            elif a in ("-W", "--no-wrapup"):
                s("DO_WRAPUP", "no")
            elif a in ("-w", "--wrapup"):
                self.do_clear_steps()
                s("DO_WRAPUP", "forced")
            elif a in ("-I", "--no-install"):
                s("DO_INSTALL", "no")
            elif a in ("-u", "--update"):
                s("DO_UPDATE", "yes")
            elif a == "--update:prefetch":
                s("DO_UPDATE", "yes")
                s("DO_PREFETCH", "yes")
            elif a in ("-s", "--setup"):
                self.do_clear_steps()
                s("DO_SETUP", "forced")
            elif a in ("-c", "--config"):
                self.do_clear_steps()
                s("DO_CONFIG", "forced")
            elif a in ("-b", "--build"):
                self.do_clear_steps()
                s("DO_BUILD", "forced")
            elif a == "--build-target":
                s("BUILD_SCBI_TARGET", nxt)
                i += 1
            elif a in ("-d", "--deps"):
                s("DEPS", "yes")
            elif a == "--deps:warning":
                s("DEPS", "yes")
                s("DO_WARNING_EXTERNAL", "yes")
            elif a in ("-i", "--install"):
                self.do_clear_steps()
                s("DO_INSTALL", "forced")
            elif a in ("-l", "--log", "--log:yes"):
                s("SCBI_DLOG", "yes")
            elif a == "--log:no":
                s("SCBI_DLOG", "no")
            elif a == "--log:on-failure":
                s("SCBI_DLOG", "on-failure")
            elif a in ("-p", "--purge"):
                s("DO_PURGE", "yes")
            elif a == "--purge:only":
                s("DO_PURGE", "only")
            elif a in ("-n", "--no-patch"):
                s("DO_PATCH", "no")
            elif a == "--prefix":
                s("SCBI_DEFAULT_PREFIX", "no")
                s("SCBI_PREFIX", nxt)
                i += 1
            elif a in ("-j", "--jobs"):
                s("SCBI_JOBS", nxt)
                i += 1
                half = nxt
                try:
                    if int(nxt) > 1:
                        half = str(int(nxt) // 2)
                except ValueError:
                    pass
                s("SCBI_HALF_JOBS", half)
            elif a == "--dry-run":
                s("DRY_RUN", "yes")
            elif a == "--safe":
                s("SAFE_MODE", "yes")
            elif a == "--standalone":
                s("DO_STANDALONE", "yes")
            elif a == "--clean-install":
                s("DO_CLEAN_INSTALL", "yes")
            elif a == "--":
                pass
            else:
                self.modules.append(a)
            i += 1

    # ------------------------------------------------------------- setup

    def tput(self, *args: str) -> str:
        try:
            return subprocess.run(["tput", *args], capture_output=True, text=True,
                                  env=self.base_env()).stdout
        except OSError:
            return ""

    def setup_colors(self) -> None:
        offset = 8 if self.get("SCBI_IS_WINDOWS") == "yes" else 0
        color = self.get("DO_COLOR")
        t = self.tput
        #  the default text color is only set on a terminal: not in the
        #  output of a pipe (scbi ini, scbi show... read by other tools)
        tty = sys.stdout.isatty()
        if color == "dark":
            if tty:
                sys.stdout.write(t("setaf", "7"))
            bold = t("bold") + t("setaf", "252")
            self.set("SCBI_CBOLD", bold)
            self.set("SCBI_CTEXT", t("setaf", "15"))
            self.set("SCBI_CCLEAR", t("sgr0") + t("setaf", "7"))
            self.set("SCBI_CRED", bold + t("setaf", str(9 - offset)))
            self.set("SCBI_CBLUE", bold + t("setaf", str(12 - offset)))
            self.set("SCBI_CGREEN", bold + t("setaf", str(10 - offset)))
        elif color == "light":
            if tty:
                sys.stdout.write(t("setaf", "0"))
            bold = t("bold") + t("setaf", "239")
            self.set("SCBI_CBOLD", bold)
            self.set("SCBI_CTEXT", t("setaf", "0"))
            self.set("SCBI_CCLEAR", t("sgr0"))
            self.set("SCBI_CRED", bold + t("setaf", "1"))
            self.set("SCBI_CBLUE", bold + t("setaf", "4"))
            self.set("SCBI_CGREEN", bold + t("setaf", "2"))

    def make_logger(self) -> Logger:
        c = {k[5:]: self.get(k) for k in ("SCBI_CBOLD", "SCBI_CTEXT", "SCBI_CRED",
                                           "SCBI_CGREEN", "SCBI_CBLUE", "SCBI_CCLEAR")}
        return Logger(Path(self.get("SCBI_LOGS")), self.get("TODAY"), self.get("SCBI_TARGET"),
                      Path(self.get("SCBI_LINE_SEP") or os.devnull), quiet=self.get("DO_QUIET") == "yes",
                      colors=c)

    def load_runtime(self) -> None:
        """The start-up settings of the runtime files (scbi.setup: the
        runtime files are not read)."""
        from scbi import setup

        forced_os = bool(self.get("SCBI_OS_NAME"))
        #  1_setup, 2_log, 5_tools, 8_mail
        for name, value in setup.defaults(self.get).items():
            #  testsuite: the test 1_setup does not set the SVN/HG
            #  repositories (given empty by tests/run)
            if not (self.testsuite and name in setup.TEST_UNSET and name in self.environ):
                self.set(name, value)
        #  testsuite: the test 1_setup does not set TODAY (logs directly in
        #  $SCBI_LOGS), given by tests/run
        if self.testsuite and "TODAY" in self.environ:
            self.set("TODAY", self.environ["TODAY"])
        else:
            self.set("TODAY", setup.today())
        if not self.get("KEEP_LOG_DAYS"):
            self.set("KEEP_LOG_DAYS", "120")
        self.set("SCBI_LINE_SEP", setup.line_sep_file())
        for name, value in setup.CONSTANTS.items():
            self.set(name, value)
        if not self.get("SCBI_EMAIL_NOTIFICATION"):
            self.set("SCBI_EMAIL_NOTIFICATION", "no")
        os.makedirs(f"{self.get('SCBI_LOGS')}/{self.get('TODAY')}", exist_ok=True)
        setup.clean_logs(self.get("SCBI_LOGS"), self.get("HOME"), self.get("KEEP_LOG_DAYS"))
        #  6_distpkg
        self.setup_os_discriminants(forced_os)
        tools = {"deb": "dpkg-query", "ubt": "dpkg-query", "cos": "dnf rpm", "fed": "dnf rpm",
                 "rhl": "dnf rpm"}.get(self.get("SCBI_OS_NAME"))
        if tools:
            self.check_tools_abort(*tools.split())
        pkgs, alias = setup.os_packages(self.get("SCBI_OS_NAME"), self.get, os.getcwd())
        self.sv.arrays["SCBI_PKGS"] = ("A", pkgs)
        self.sv.arrays["SCBI_ALIAS"] = ("A", alias)
        #  _os_windows
        if self.get("SCBI_OS_MODULE") == "windows" and self.get("SCBI_OS_NAME") == "mingw":
            self.set("SCBI_LNK", ".lnk")

        #  the define-var of _os_windows
        env_mod.WINDOWS_DEFINE_VAR = self.get("SCBI_OS_MODULE") == "windows"

    def check_tools_abort(self, *tools: str) -> None:
        missing = [t for t in tools if not self.which(t)]
        if missing:
            self.echo(f"Required tools {' '.join(missing)} missing, please install")
            raise Exit(1)

    def setup_os_discriminants(self, forced: bool) -> None:
        """SCBI_OS_NAME and SCBI_OS_DISCRIMINANTS as set by
        scripts.d/6_distpkg (the OS can be forced by setting SCBI_OS_NAME
        before, e.g. in the testsuite)."""
        if self.get("SCBI_IS_WINDOWS") == "no":
            self.check_tools_abort("lsb_release")
        if forced:
            self.discriminants = forced_discriminants(
                self.get("SCBI_OS_NAME"), self.get("SCBI_OS_VERSION"), self.get("SCBI_OS_MAJOR_VERSION"))
            return
        info = setup_discriminants(probe_host(), self.get("SCBI_HOST"), self.get("SCBI_TARGET"))
        self.set("SCBI_OS_NAME", info.name, export=True)
        self.set("SCBI_OS_VERSION", info.version, export=True)
        self.set("SCBI_OS_CODENAME", info.codename, export=True)
        self.set("SCBI_OS_MAJOR_VERSION", info.major_version, export=True)
        self.set("SCBI_OS_ID", info.os_id, export=True)
        self.discriminants = info.discriminants

    def module_plan_md5(self, nameref: str) -> str:
        """Port of ``module-plan-md5``."""
        sig = ""
        seen: set[str] = set()
        plugins = Path(self.get("SCBI_PLUGINS"))

        def inner(nameref: str) -> None:
            nonlocal sig
            name = nameref if "/" not in nameref else nameref.rsplit("/", 1)[0]
            if name in seen:
                return
            seen.add(name)
            plan = Path.cwd() / f".scbi-plan-{name}"
            if not plan.is_file():
                plan = plugins / f".plan-{name}"
            if plan.is_file():
                text = plan.read_text()
                sig += text.rstrip("\n")
                for line in read_lines(text):
                    f = words(line)
                    if len(f) > 1 and f[0] == "@load":
                        inner(f[1])
            sig = md5_echo(f"{nameref} {sig}")

        if nameref:
            inner(nameref)
        return sig

    def install_md5(self) -> str:
        """Port of ``get-install-md5`` (signature of the OS packages log)."""
        logs = {"deb": "/var/log/apt/history.log", "ubt": "/var/log/apt/history.log",
                "cos": "/var/log/dnf.log", "rhl": "/var/log/dnf.log", "fed": "/var/log/dnf.log",
                "mingw": "/var/log/pacman.log"}
        name = self.get("SCBI_OS_NAME")
        if name == "win":
            return ""
        log = logs.get(name)
        if log is None:
            return ""
        if os.access(log, os.R_OK):
            return hashlib.md5(Path(log).read_bytes()).hexdigest()
        return md5_echo(str(int(time.time())))

    # ----------------------------------------------------------- displays

    def usage(self) -> None:
        self.echo()
        self.echo(f"SCBI {self.get('SCBI_VERSION')}")
        self.echo()
        self.echo(f"{self.argv0} [options] module1 [module2 ... modulen]")
        self.echo(USAGE_OPTIONS.format(target=self.get("SCBI_TARGET")))

    def display_stat(self) -> None:
        home = self.get("HOME")

        def d(v: str) -> str:
            return " ".join(words(v.replace(home, "~"))) if home else v

        def row(name: str, value: str) -> None:
            self.echo(f"{name:<21} : {value}")

        self.echo(f"SCBI : {self.get('SCBI_VERSION')}")
        self.echo()
        self.echo("stats")
        self.echo("-----")
        if self.get("SCBI_IS_WINDOWS") == "yes":
            row("host", "windows")
        else:
            desc = subprocess.run(["lsb_release", "-s", "-d"], capture_output=True, text=True).stdout
            row("host", desc.rstrip("\n"))
        self.echo(f"{'':<21}   {self.get('SCBI_HOST')}")
        if self.get("SCBI_HOST") != self.get("SCBI_TARGET"):
            row("target", self.get("SCBI_TARGET"))
        for name, var in (("build dir", "SCBI_BDIR"), ("install prefix", "SCBI_PREFIX"),
                          ("archive dir", "SCBI_ARCHIVES"), ("patches dir", "SCBI_PATCH"),
                          ("user's Git repository", "SCBI_GIT_REPO"),
                          ("user's SVN repository", "SCBI_SVN_REPO"), ("plug-ins dir", "SCBI_PLUGINS")):
            row(name, d(self.get(var)))
        row("plan", d(self.get("SCBI_PLAN") or "no"))
        email = "no" if self.get("SCBI_EMAIL_NOTIFICATION") == "no" else self.get("SCBI_EMAIL")
        row("e-mail notification", email)
        row("supported platforms", " ".join(OS_NAMES))
        discs = " ".join(assoc_keys(self.discriminants))
        sys.stdout.write(f"{'discriminants':<21} :")
        fmt_first = True
        for line in _fold(discs, 50):
            if fmt_first:
                self.echo(f" {line}")
                fmt_first = False
            else:
                self.echo(f"{'':<24}{line}")
        self.echo()

    def display_names(self, title: str, names: list[str]) -> None:
        out = title
        linelen = 0
        for bn in names:
            linelen += len(bn) + 1
            if linelen > 70:
                out += "\n        "
                linelen = len(bn)
            out += f" {bn}"
        self.echo(out)

    def display_modules(self) -> None:
        plugins = Path(self.get("SCBI_PLUGINS"))
        #  Bash pathname expansion: no dot-files
        #  (a plug-in definition file gives its module name)
        names = sorted({formats.module_name(p.name) for p in plugins.glob("[!0-9_]*")
                        if not p.name.startswith(".")})
        self.display_names("modules:", names)
        self.echo()

    def display_plans(self) -> None:
        plugins = Path(self.get("SCBI_PLUGINS"))
        plans = sorted(p.name for p in plugins.glob(".plan-*"))
        if not plans:
            self.echo("plans  : none")
            return
        out = "plans  :"
        linelen = 0
        for bn in plans:
            linelen += len(bn) + 1
            if linelen > 70:
                out += "\n        "
                linelen = len(bn)
            out += " " + bn.replace(".plan-", "", 1)
        self.echo(out)

    # ------------------------------------------------- setup-generic-tool-env

    def setup_generic_tool_env(self) -> None:
        self.setup_colors()

        plugins = self.get("SCBI_PLUGINS")
        if not is_plugins_dir(plugins):
            self.set("SCBI_PLUGINS", f"{self.get('HOME')}/.config/scbi", export=True)
        if not os.path.isdir(self.get("SCBI_PLUGINS")):
            self.echo(f"{self.argv0}: cannot find module definition files")
            raise Exit(1)

        #  the environment file (ENV_NAME as given, see load-module-env): a
        #  YAML file (scbi.envyaml)
        try:
            self.envfile = envyaml.load(self.get("ENV_NAME"), Path.cwd(), Path(self.get("HOME") or "/"),
                                        Path(self.get("SCBI_PLUGINS")), dict(self.sv.values))
        except envyaml.EnvFileError as e:
            self.echo(str(e))
            raise Exit(1) from None
        if self.envfile.path is not None:
            self.set("SCBI_ENV_DIR", str(self.envfile.path.parent), export=True)
        for name, value in self.envfile.settings.items():
            self.set(name, value, export=True)
        self.envfile.bind(self)
        env_mod.USER_DEFINE_VAR = self.envfile.hook("define_var")

        if self.cmdline.get("SCBI_BDIR"):
            self.set("SCBI_BDIR", self.cmdline["SCBI_BDIR"])
        if self.cmdline.get("DO_FLAT"):
            self.set("DO_FLAT", self.cmdline["DO_FLAT"])

        self.load_runtime()
        self.log = self.make_logger()

        if self.get("DO_VERSION") == "yes":
            self.echo(f"SCBI : {self.get('SCBI_VERSION')}")
            for f in sorted(Path(self.get("SCBI_PLUGINS")).glob(".scbi*version.txt")):
                sys.stdout.write(f.read_text())
            raise Exit(0)

        if self.cmdline.get("SCBI_PLAN"):
            self.set("SCBI_PLAN", self.cmdline["SCBI_PLAN"])

        bdir = self.get("SCBI_BDIR")
        if self.get("DO_CLEAR_CACHE") == "yes":
            shutil.rmtree(f"{bdir}/.cache", ignore_errors=True)
            if self.get("SCBI_CACHE_DIR"):
                for p in Path(self.get("SCBI_CACHE_DIR")).glob("*"):
                    shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()

        #  Plan cache key
        planmd5 = self.module_plan_md5(self.get("SCBI_PLAN"))
        osmd5 = self.install_md5()
        msig = ""
        plugins = Path(self.get("SCBI_PLUGINS"))
        for m in self.modules:
            info = (self.plan.module_ref(m) + [""] * 4)[:4]
            module, variant, ref = info[0], info[1], info[3]
            if variant != "default" or ref != "NONE":
                msig += f"({m}/{variant}/{ref})"
            pfile = formats.find(plugins, module)
            if pfile is not None:
                msig += pfile.read_text().rstrip("\n")
        discs_values = " ".join("yes" for _ in self.discriminants)
        planmd5 = md5_echo(
            f"{planmd5} {osmd5} {self.get('SCBI_TARGET')} {self.get('SCBI_OS_ID')} "
            f"{self.get('SCBI_OS_NAME')} {self.get('SCBI_OS_VERSION')} "
            f"{self.get('SCBI_OS_MAJOR_VERSION')} {discs_values} {msig}")
        os.makedirs(f"{bdir}/.cache", exist_ok=True)
        #  JSON, a different name from the Bash driver cache (declare -p)
        cached_plan = Path(f"{bdir}/.cache/plan-{planmd5}.json")

        plan_cached = False
        if cached_plan.is_file():
            plan_cached = True
            self.load_cached_plan(cached_plan)
        elif self.get("SCBI_PLAN"):
            loader = PlanLoader(self.plan, plugins, self.discriminants, Path.cwd(), self.is_built)
            try:
                loader.load(self.get("SCBI_PLAN"))
            except PlanError as e:
                self.log.elog(e.module, e.message)
                raise Exit(1) from None

        subcmd = self.get("DO_SUBCMD") == "yes"
        stat = self.get("DO_STAT")
        if not subcmd:
            if not self.modules and stat == "no":
                self.usage()
                raise Exit(0)
            if self.get("DO_HELP") == "yes":
                self.usage()
                raise Exit(0)

        if stat != "no":
            self.display_stat()

        if not subcmd:
            if not self.modules and stat != "short":
                self.display_modules()
                self.display_plans()
            if stat == "full":
                self.display_log_stat()
            elif not self.modules and stat == "yes":
                self.echo()

        #  module references of the command line
        #  for module in ${SCBI_MODULES[*]} ... SCBI_MODULES=(${SMT[*]}):
        #  unquoted, an argument with blanks gives several modules
        smt = []
        for module in words(" ".join(self.modules)):
            if "@" in module:
                r = (parse_module_ref(module).to_bash_array() + [""] * 4)
                mname = r[0]
                r = (self.plan.module_ref(mname) + [""] * 4)
                mvar, mver = r[1], r[3]
                if mvar == "default":
                    module = module.replace("/@", "", 1)
                else:
                    module = module.replace("/@", f"/{mvar}", 1)
                module = module.replace(":@", f":{mver}", 1)
            smt.append(module)
            self.set_module_ref(module)
        self.modules = words(" ".join(smt))

        if plan_cached:
            if (not subcmd or stat != "no") and self.plan.modver:
                self.log.ilog("build", f"Using cached module plan ({planmd5[:20]})")
                self.log.line_sep()
        else:
            if not subcmd or stat != "no":
                res = self.rewrite_module_plan()
                self.log.line_sep()
            else:
                res = self.rewrite_module_plan(quiet=True)
            if res == 1:
                raise Exit(1)
            self.store_cached_plan(cached_plan)

    # ------------------------------------------------------------ plug-ins

    @property
    def registry(self):
        from scbi.plugin.registry import Registry

        if self._registry is None:
            self._registry = Registry(Path(self.get("SCBI_PLUGINS")), module_alias=self.plan.module_alias,
                                      read_legacy=False)
        return self._registry

    def runner(self):
        from scbi.hooks.runner import HookRunner

        if self._runner is None:
            self._runner = HookRunner(
                self.registry, lambda: self.sv, self.base_env,
                self.get("SCBI_HOST"), self.get("SCBI_TARGET"), lambda: self.discriminants, Path.cwd())
        return self._runner

    # --------------------------------------------------------------- plan

    def is_built(self, module: str, variant: str) -> bool:
        tdf = f"{self.get('SCBI_BDIR')}/{module}/{self.get('SCBI_TARGET')}-{variant}"
        return os.path.isdir(f"{tdf}/install")

    def set_module_ref(self, modref: str) -> None:
        """Port of ``set-module-ref``."""
        r = (parse_module_ref(modref).to_bash_array() + [""] * 4)
        module, variant, kind, ref = r[:4]
        if variant != "default" or kind.upper() != "NONE" or ref.upper() != "NONE":
            self.plan.register(["set", *words(module), *words(re.sub(r"^.*=", "", modref, flags=re.S)),
                                *words(ref)], self.is_built)

    def rewrite_module_plan(self, quiet: bool = False) -> int:
        """Port of ``rewrite-module-plan``: auto variants, then the
        meta-modules propagation."""
        from scbi.metaplan import propagate_meta_versions

        eres = 0
        auto = [m for m in assoc_keys(self.plan.modver)
                if re.search(r"auto(\.|:|$)", self.plan.modver[m])]
        #  handle-plan-auto-variant for each module, all against the plan as
        #  it is now (parallel jobs in Bash)
        from scbi import ospkg
        from scbi.build import Builder

        outputs: list[str] = []
        builder = Builder(self)
        for m in auto:
            outputs += ospkg.OsPackages(self).plan_auto_variant(builder, m)
        for line in outputs:
            f = read_fields(line, 3)
            e, k, v = f
            if e == "0":
                self.plan.register(["auto", *words(k), *words(v)], self.is_built)
            elif e == "1":
                #  the report log of the module (k: <formodule>=<module>
                #  for a module referenced with @for)
                if not quiet:
                    self.log.ilog(k.rsplit("=", 1)[-1], v)
            else:
                #  an error (stderr) is shown even when quiet (> /dev/null)
                self.log.elog(k.rsplit("=", 1)[-1], v)
                eres = 1
        res = propagate_meta_versions(self)
        return eres or res

    def display_log_stat(self) -> None:
        """``display-log-stat``: build times from the report logs."""
        from scbi.log import display_log_stat

        sys.stdout.write(display_log_stat(Path(self.get("SCBI_LOGS"))))
        sys.stdout.flush()

    def run_tool(self, subcmd: str) -> int:
        """A sub-command (scbi.tools)."""
        import importlib

        from scbi.tools import TOOLS

        sys.stdout.flush()
        res = importlib.import_module(TOOLS[subcmd]).main(self, self.scbiopts + self.modules)
        return res or 0

    def store_cached_plan(self, path: Path) -> None:
        import json

        path.write_text(json.dumps({"modver": self.plan.modver, "hist": self.plan.plan_hist}))

    def load_cached_plan(self, path: Path) -> None:
        import json

        try:
            data = json.loads(path.read_text())
        except ValueError:
            return
        self.plan.modver.update(data.get("modver", {}))
        self.plan.plan_hist.update(data.get("hist", {}))

    # ---------------------------------------------------------------- main

    def main(self, args: list[str]) -> int:
        self.init_globals()
        self.ini_load_files()
        self.ini_apply_values("")
        self.first_pass(args)
        if self.environ.get("SCBI_NESTED") == "yes":
            #  a run of the driver for a host@ dependency (scbi.build): only
            #  the modules of its command line, no stats
            self.ini_modules = []
            self.set("DO_STAT", "no")
        self.modules += self.ini_modules

        subcmd = self.ini_subcmd or (self.modules[0] if self.modules else "")
        from scbi.tools import TOOLS

        has_subcmd = subcmd in TOOLS
        if has_subcmd:
            self.set("DO_SUBCMD", "yes", export=True)
            if not self.ini_subcmd:
                self.modules.pop(0)
            self.ini_apply_values(f"scbi-{subcmd}")

        for name, value in self.cmdline.items():
            self.set(name, value)

        if has_subcmd:
            if subcmd == "replay" and {"--script", "--script:inline"} & set(self.scbiopts + self.modules) \
                    or subcmd in ("schema", "ini"):
                #  the output is a script, a schema or the list of the ini
                #  sections (read by a program): no stats nor plan messages
                self.set("DO_STAT", "no")
            self.setup_generic_tool_env()
            return self.run_tool(subcmd)

        self.second_pass()

        steps = ""
        for step, var in (("setup", "DO_SETUP"), ("config", "DO_CONFIG"), ("build", "DO_BUILD"),
                          ("install", "DO_INSTALL"), ("tests", "DO_TEST"), ("wrapup", "DO_WRAPUP")):
            if self.get(var) != "no":
                steps += f" {step}"
        self.set("STEPS", steps)

        self.setup_generic_tool_env()

        os.makedirs(f"{self.get('SCBI_LOGS')}/{self.get('TODAY')}", exist_ok=True)
        os.makedirs(self.get("SCBI_ARCHIVES") or ".", exist_ok=True)

        if self.get("DRY_RUN") == "yes":
            for v in ("DO_PURGE", "DO_INSTALL", "DO_ARCHIVE", "DO_UPDATE", "DO_FORCE", "DO_CLEAN_INSTALL"):
                self.set(v, "no")
            self.set("STEPS", "")

        bdir = Path(self.get("SCBI_BDIR"))
        bdir.mkdir(parents=True, exist_ok=True)

        from scbi.build import Builder

        builder = Builder(self)
        #  a module given twice is built once
        self.modules = list(dict.fromkeys(self.modules))
        if self.get("DEPS") != "yes" and len(self.modules) > 1:
            #  without --deps the modules are built in the order of the
            #  command line: a module after its dependencies
            from scbi.walker import build_order

            order = build_order(builder, self.modules)
            if order != self.modules:
                self.log.ilog("build", "build order:", *order)
                self.modules = order
        restore = self.start_progress(builder)
        try:
            self.start_prefetch(builder)
            for module in self.modules:
                builder.handle_module("@root", module, "default", "no")
        finally:
            if builder.prefetcher is not None:
                builder.prefetcher.shutdown()
                builder.prefetcher = None
            self.progress.close()
            restore()

        if self.get("DO_STANDALONE") == "yes":
            from scbi.standalone import Standalone

            Standalone(builder).create(self.modules)
        return 0

    # ------------------------------------------------------------ progress

    def start_progress(self, builder):
        """The build progress ``[n/N] module``, only when the output is a
        terminal (not with --quiet, SCBI_PROGRESS=no or in the testsuite):
        --progress[:bar|line|no] or SCBI_PROGRESS: bar (default) a status
        bar on the last row with the elapsed time (scbi.log.StatusBar),
        line a transient last line (scbi.log.StatusLine). Returns the function restoring
        the console streams."""
        from scbi.log import Progress, StatusBar, StatusLine, StatusStream

        out = sys.stdout
        mode = self.get("SCBI_PROGRESS")
        if self.testsuite and self.environ.get("SCBI_TEST_PROGRESS") == "yes":
            #  testsuite: each step of the progress printed on a line
            class Lines:
                def set(self, text: str) -> None:
                    print(f"progress {text}", file=sys.stdout, flush=True)

                def clear(self) -> None:
                    pass

            self.progress = Progress(Lines(), self.progress_total(builder))
            return lambda: None
        if (not out.isatty() or self.testsuite or self.get("DO_QUIET") == "yes" or mode == "no"):
            self.progress = Progress()
            return lambda: None
        status = StatusLine(out) if mode == "line" else StatusBar(out)
        saved = (sys.stdout, sys.stderr, self.log.stdout, self.log.stderr)
        sys.stdout = self.log.stdout = StatusStream(out, status)
        if sys.stderr.isatty():
            sys.stderr = self.log.stderr = StatusStream(sys.stderr, status)

        def restore() -> None:
            sys.stdout, sys.stderr, self.log.stdout, self.log.stderr = saved

        if isinstance(status, StatusBar):
            status.begin()
        self.progress = Progress(status, self.progress_total(builder))
        return restore

    def start_prefetch(self, builder) -> None:
        """--update:prefetch: the network part of the update of the sources
        of the modules of the build done ahead, by SCBI_PREFETCH_JOBS
        threads (default 4, 0: no prefetch)."""
        if self.get("DO_PREFETCH") != "yes" or self.get("DO_UPDATE") != "yes":
            return
        from scbi.sources.prefetch import DEFAULT_JOBS, Prefetcher

        try:
            jobs = int(self.get("SCBI_PREFETCH_JOBS") or DEFAULT_JOBS)
        except ValueError:
            jobs = DEFAULT_JOBS
        if jobs <= 0:
            return
        builder.prefetcher = Prefetcher(builder, jobs)
        builder.prefetcher.start(self.planned_modules(builder))

    def progress_total(self, builder) -> int:
        """The number of modules the build will handle (planned_modules)."""
        return len(self.planned_modules(builder))

    def planned_modules(self, builder) -> list[tuple[str, str, str, str, str]]:
        """The modules the build will handle, in order: the modules of the
        command line, the modules of their meta-modules and, with --deps,
        their dependencies (plug-ins only, not the skipped ones), as
        (formodule, module, variant, kind, ref). Computed once."""
        if self._planned is not None:
            return self._planned
        from scbi.walker import Walker

        found: dict[str, tuple[str, str, str, str, str]] = {}
        prefix, target = self.get("SCBI_PREFIX"), self.get("SCBI_TARGET")

        def metas(walker: Walker, modref: str, formodule: str) -> None:
            module, variant, kind, ref = walker.module_info(modref, formodule)
            key = f"{module}+{variant}+{ref}"
            if ref == "skip" or key in found or not walker.load_module(modref):
                return
            found[key] = (formodule, module, variant, kind, ref)
            for m in words("\n".join(self.runner().variant_values(
                    module, variant, "modules", [prefix, target, variant], self.plan, builder.modules_list))):
                metas(walker, m, module)

        try:
            for module in self.modules:
                walker = Walker(builder)
                if self.get("DEPS") == "no":
                    metas(walker, module, "@root")
                    continue

                def callback(argv: list[str], walker=walker) -> int:
                    a = argv + [""] * 5
                    if a[4] == "true":  # an external package
                        return 0
                    if builder.is_host_dep(a[1]):  # built by a run for the host
                        return 0
                    m, v, kind, ref = walker.module_info(a[1], a[0])
                    if ref != "skip":
                        found.setdefault(f"{m}+{v}+{ref}", (a[0], m, v, kind, ref))
                    return 0

                walker.walk("for-all-modules-with-meta-ext", callback, module)
        except Exit:
            #  reported when the module is built
            pass
        self._planned = list(found.values())
        return self._planned

    def clean_up(self) -> None:
        for v in ("SCBI_HANDLED", "SCBI_LINE_SEP"):
            p = self.get(v)
            if p:
                try:
                    os.unlink(p)
                except OSError:
                    pass


def _fold(text: str, width: int) -> list[str]:
    """``fold -s -w width`` for a single line of words."""
    lines: list[str] = []
    cur = ""
    for w in text.split(" "):
        candidate = f"{cur}{w} " if cur or w else cur
        if len(candidate) > width and cur:
            lines.append(cur)
            cur = f"{w} "
        else:
            cur = candidate
    if cur:
        lines.append(cur)
    #  fold keeps the trailing blank of each broken line; read removes it
    return [ln.strip(" ") for ln in lines]
