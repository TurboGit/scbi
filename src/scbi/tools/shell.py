"""scbi shell: a shell or a command in the environment of modules (port
of scbi-shell).

The options, the checks and the choice of the directory are done here.
Setting up the environment (handle-env..., the env hooks of the
plug-ins, user redefinitions of define-var), exporting the functions and
spawning $SHELL are Bash work: they run in a hook shell attached to the
terminal, with the reference functions of the driver and the runtime.
"""

from __future__ import annotations

import subprocess
import sys

from scbi.bashcompat import words
from scbi.hooks.exec import quote

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


def setup_env(modref: str, info: list[str], modules: list[str], docd: str, mode: str) -> str:
    """Bash code of ``shl-setup-env``."""
    q = quote
    code = ['if [[ "$SCBI_HOST" != "$SCBI_TARGET" ]]; then target-env $SCBI_BDIR/install $SCBI_TARGET; fi']
    for m in modules:
        code.append(f"handle-env @root {q(m)}\nhandle-module-env @root {q(m)} env")
    code.append(f"SHL_MODULE={q(info[0])}\nSHL_VARIANT={q(info[1])}\nSHL_KIND={q(info[2])}")
    code.append(f"export SCBI_SHELL={q(mode)}:$SHL_MODULE")
    if docd in ("yes", "yes-dev"):
        code.append(f"handle-build-depends-env @root {q(modref)}")
    if docd == "yes-tests":
        code.append(f"handle-tests-depends-env @root {q(modref)}\n"
                    f"handle-module-env @root {q(modref)} tests-env")
    code.append(f"handle-env @root {q(modref)}")
    if docd in ("yes", "yes-dev"):
        code.append(f"handle-module-env @root {q(modref)} build-env")
    if docd in ("yes-nocd", "yes-tests"):
        code.append(f"handle-module-env @root {q(modref)} env")
    return "\n".join(code)


def main(driver, args: list[str]) -> int:
    do_run, run_cmd = "no", ""
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

    #  run as the Bash tool does: state of the tool shell
    driver.set("DO_WARNING_EXTERNAL", "yes")
    target = driver.get("SCBI_TARGET")
    modref = modules[-1]
    info = (driver.plan.module_ref(modref) + [""] * 4)[:4]
    shl_module, shl_variant, shl_kind = info[:3]
    q = quote

    code = [
        f"DO_EXT=no\nDO_LIST_VER=yes-nocd\nDO_MOD_VER=no\nDO_SHELL={q(docd)}\nDO_MODE={q(mode)}\n"
        f"DO_WARNING_EXTERNAL=yes\nSCBI_FILTER=all\nSHL_MODULE=''\nSHL_VARIANT=''\nSHL_KIND=''\n"
        f"DO_RUN={'yes' if do_run == 'yes' else ''}\nDO_RUN_CMD={q(run_cmd)}",
        "declare -A SCBI_MODULES_DIR=()",
        'if [[ -z $SHELL ]]; then echo \\$SHELL is not defined, cannot spawn a shell; exit 1; fi',
    ]

    if do_run == "yes":
        code.append(setup_env(modref, info, modules[:-1], docd, mode))
        if not run_cmd:
            prefix = f"$SCBI_BDIR/{q(shl_module)}/{q(target)}-{q(shl_variant)}/install"
            code.append(
                f"CMD=''\nPREFIX={prefix}\nHOOKS=()\n"
                f"plugin-get-variant-hooks HOOKS {q(shl_module)} run $PREFIX {q(target)} {q(shl_variant)}\n"
                'for H in ${HOOKS[*]}; do declare -fx $H; CMD+="$H; "; done\n'
                f"[[ -z $CMD ]] && elog {q(shl_module)} no command specified for run option")
        else:
            code.append(f"CMD={q(run_cmd)}")
        code.append("eval \"$(declare -F | sed -e 's/-f /-fx /')\"\n"
                    '$SHELL -c "$CMD"\nexit 0')
    else:
        code.append("curcd=$(pwd)\nDIR=''")
        code.append(setup_env(modref, info, modules[:-1], docd, mode))
        if docd == "yes-nocd":
            code.append("cd $curcd")
        elif shl_kind == "DEV" or docd == "yes-dev":
            code.append(
                f"if is-meta-module {q(modref)} > /dev/null; then DIR=$PWD\n"
                f"else DIR=$(get-vcs-dir {q(shl_module)}:dev)\n"
                f"  if [[ ! -d $DIR ]]; then DIR=''; elog {q(shl_module)} no user checkout directory $DIR; fi\n"
                "fi")
        else:
            code.append(f"DIR=$(get-build-dir {q(target)} {q(modref)})")
        code.append('[[ -n $DIR ]] && { PFX=${curcd#$DIR}; [[ $PFX == $curcd ]] && cd $DIR; }')
        code.append("eval \"$(declare -F | sed -e 's/-f /-fx /')\"\n$SHELL\nexit 0")

    from scbi.hooks.exec import run_interactive

    sys.stdout.flush()
    shell, ctx = driver.driver_shell()
    return run_interactive(shell, ctx, "\n".join(code))
