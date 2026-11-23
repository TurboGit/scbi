"""scbi shell: a shell or a command in the environment of modules (port
of scbi-shell).

The environment is computed by the driver (scbi.steps.modenv); then the
user's $SHELL is spawned (or ``$SHELL -c CMD`` for ``--run=CMD``). The
``run`` hooks of a module (``--run`` without a command) are interpreted
(command language).
"""

from __future__ import annotations

import os
import subprocess
import sys

from scbi.bashcompat import words

USAGE = """
SCBI-SHELL {version}

{argv0} shell [options] plug-in1 [plug-in2...]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --plugins=<dir>    specify the plugins' directory
   -e | --env=<name>       environment file ~/.scbi-<name>
      | --build-dir=<dir>  the root build directory.
      | --mode:n           start a shell with module's environment
      | --run="cmd arg"    run command in module's environment
      | --stat             display some status of current setup"""

MODES = {
    "--mode:sb": ("yes", "s"), "--mode:sandbox": ("yes", "s"),
    "--mode:dev": ("yes-dev", "d"), "--mode:tests": ("yes-tests", "t"),
    "--mode:use": ("yes-nocd", "u"),
}


def setup_env(modref: str, modules: list[str], docd: str) -> list[tuple]:
    """The environment calls of ``shl-setup-env`` (scbi.steps.modenv)."""
    calls: list[tuple] = []
    for m in modules:
        calls += [("handle-env", "@root", m), ("module-env", "@root", m, "env")]
    if docd in ("yes", "yes-dev"):
        calls.append(("handle-build-depends-env", "@root", modref))
    if docd == "yes-tests":
        calls += [("handle-tests-depends-env", "@root", modref), ("module-env", "@root", modref, "tests-env")]
    calls.append(("handle-env", "@root", modref))
    if docd in ("yes", "yes-dev"):
        calls.append(("module-env", "@root", modref, "build-env"))
    if docd in ("yes-nocd", "yes-tests"):
        calls.append(("module-env", "@root", modref, "env"))
    return calls


def main(driver, args: list[str]) -> int:
    #  the run option of an ini section (DO_RUN, DO_RUN_CMD set by the
    #  driver), overridden by --run on the command line
    do_run, run_cmd = driver.get("DO_RUN") or "no", driver.get("DO_RUN_CMD") or ""
    opts: list[str] = []
    for a in args:
        if a.startswith("--run="):
            #  ${1/*=/}: up to the last "="
            do_run, run_cmd = "yes", a.rsplit("=", 1)[1]
        elif a == "--run":
            do_run, run_cmd = "yes", ""
        elif a.startswith("-"):
            opts += words(a)

    proc = subprocess.run(
        ["getopt", "-u", "-o", "kld", "-l", "mode:use,mode:dev,mode:tests,mode:sb,mode:sandbox",
         "--", *words(" ".join(opts))],
        capture_output=True, text=True, env=driver.base_env())
    if proc.returncode != 0:
        sys.stdout.write(proc.stderr)
        print('try "scbi shell --help" for more information.')
        return 1

    docd, mode = "yes-nocd", "u"
    for a in words(proc.stdout):
        if a in MODES:
            docd, mode = MODES[a]

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0

    modules = words(" ".join(driver.modules))
    if not modules:
        print("error: shell/run commands need a plug-in, see scbi shell --help")
        return 0

    #  state of the Bash tool
    driver.set("DO_WARNING_EXTERNAL", "yes")
    shell = driver.get("SHELL")
    if not shell:
        print("$SHELL is not defined, cannot spawn a shell")
        return 1

    from scbi.build import Builder
    from scbi.env import Environment
    from scbi.steps import interp
    from scbi.steps.modenv import ModuleEnv

    builder = Builder(driver)
    target = driver.get("SCBI_TARGET")
    modref = modules[-1]
    shl_module, shl_variant, shl_kind = (driver.plan.module_ref(modref) + [""] * 4)[:3]
    curcd = os.getcwd()

    env = Environment(driver.sv.copy())
    me = ModuleEnv(builder, env)
    me.env.export("SCBI_SHELL", f"{mode}:{shl_module}")
    rc = me.run(setup_env(modref, modules[:-1], docd))
    if rc != 0:
        return rc
    sv = me.env.vars
    environ = sv.environ()
    sys.stdout.flush()

    if do_run == "yes":
        if run_cmd:
            return _spawn([shell, "-c", run_cmd], environ, curcd)
        prefix = f"{driver.get('SCBI_BDIR')}/{shl_module}/{target}-{shl_variant}/install"
        from scbi.plugin.resolve import variant_hooks

        fcts = variant_hooks(driver.registry, shl_module, "run", shl_variant, driver.runner().cross)
        if not fcts:
            driver.log.elog(shl_module, "no", "command", "specified", "for", "run", "option")
            return 0
        for fct in fcts:
            hook = interp.Hook(builder, shl_module, shl_variant, fct, [prefix, target, shl_variant], curcd, sv)
            hook.run(lambda text: (sys.stdout.write(text), sys.stdout.flush()),
                     err=lambda text: (sys.stderr.write(text), sys.stderr.flush()))
        return 0

    cwd = curcd
    if docd != "yes-nocd":
        if shl_kind == "DEV" or docd == "yes-dev":
            if me.is_meta_module(modref):
                tdir = curcd
            else:
                from scbi.sources.data import vcs_dir

                tdir, _ = vcs_dir(builder, f"{shl_module}:dev")
                if not os.path.isdir(tdir):
                    #  (Bash: DIR is emptied before the message)
                    tdir = ""
                    driver.log.elog(shl_module, "no", "user", "checkout", "directory")
        else:
            tdir = f"{builder.target_dir(shl_module, shl_variant)}/build"
        #  stay in a sub-directory of the module's directory
        if tdir and not curcd.startswith(tdir):
            if os.path.isdir(tdir):
                cwd = tdir
            else:
                #  cd fails, the shell starts in the current directory
                sys.stdout.flush()
                print(f"cd: {tdir}: No such file or directory", file=sys.stderr)
    return _spawn([shell], environ, cwd)


def _spawn(argv: list[str], environ: dict[str, str], cwd: str) -> int:
    try:
        subprocess.run(argv, env=environ, cwd=cwd)
    except OSError as e:
        print(f"{argv[0]}: {e.strerror}")
        return 1
    return 0
