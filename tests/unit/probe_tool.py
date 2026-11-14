"""Test-only sub-command ``scbi probe <command> args...``: runs a ported
runtime function and prints its result; tests compare it with the same
command of the Bash script scbi-probe (PROBE_SCRIPT) running the
reference Bash function.

Commands (several separated by @@):
  walk ENTRY MODREF                       for-all-modules* + recording callback
  vcs-data MODULE VARIANT                 get-vcs-data
  archive-data MODULE VARIANT VERSION     get-archive-data
  archive-exists MODULE VARIANT VERSION   check-archive-exists
  vcs-dir MODREF                          get-vcs-dir
  build-id FORMODULE MODREF VID           get-build-id $SCBI_PREFIX $SCBI_TARGET ...
  depends-build-id MODREF                 get-depends-build-id
  patch-md5 FILE                          get-patch-md5
  handle-sources FORMODULE MODREF         handle-sources (in $SCBI_BDIR/MODULE)
  get-archive MODULE VARIANT VERSION      get-archive (in $SCBI_BDIR/MODULE, as
                                          handle-sources: 2>>$log | tee -a $log)
  generic STEP FORMODULE MODREF OOT       module-STEP as the driver runs it
                                          (2>&1 | tee -a $log, purge: no tee)
  wrapper STEP MODREF OOT                 module-variant-wrapper (the target
                                          directory and its logs created)
  env KIND FORMODULE MODREF               handle-env (KIND env), handle-build-
                                          depends-env (build), handle-tests-
                                          depends-env (tests) or handle-module-
                                          env FORMODULE MODREF KIND (other
                                          KIND): the define-var records, the
                                          modules dirs and the variables set
  check-pkg PKG[:VERSION]                 check-pkg (messages and status)
  pkg-status PKG[:VERSION]                check-pkg-status
  auto M                                  handle-plan-auto-variant (M: a key
                                          of the plan)
"""

import sys

from scbi.bashcompat import words
from scbi.build import Builder
from scbi.sources import buildid, data
from scbi.walker import Walker

PROBE_SCRIPT = r"""#!/bin/bash
[[ $1 == subcommand ]] && shift
set -- ${SCBI_MODULES[*]}

function run1()
{
cmd=$1
shift
case $cmd in
    walk)
        cb() { echo "CB $*"; }
        $1 cb $2 x1 x2
        echo "rc=$?"
        ;;
    vcs-data)
        load-module $1
        r=( $(get-vcs-data $1 $2) )
        echo "rc=$? ${r[*]}"
        ;;
    archive-data)
        load-module $1
        module=$1
        r=( $(get-archive-data $1 $2 $3) )
        echo "rc=$? ${r[*]}"
        ;;
    archive-exists)
        load-module $1
        module=$1
        check-archive-exists $1 $2 $3
        echo "rc=$?"
        ;;
    vcs-dir)
        load-module $1
        r=$(get-vcs-dir $1)
        echo "rc=$? $r"
        ;;
    build-id)
        load-module $2
        r=$(get-build-id "$SCBI_PREFIX" "$SCBI_TARGET" $1 $2 "$3")
        echo "rc=$? $r"
        ;;
    depends-build-id)
        load-module $1
        r=$(get-depends-build-id $1)
        echo "rc=$? $r"
        ;;
    patch-md5)
        echo "$(get-patch-md5 $1)"
        ;;
    handle-sources)
        load-module $2
        mi=()
        get-module-ref mi $2 $1
        m=${mi[0]}
        mkdir -p $SCBI_BDIR/$m
        log=$SCBI_BDIR/$m.log
        (cd $SCBI_BDIR/$m; for f in src vcs; do [[ -L $f ]] && rm -f $f; done
         trap 'echo "rc=$? DO_UPDATE=$DO_UPDATE"' EXIT
         handle-sources $1 $2)
        ;;
    get-archive)
        load-module $1
        module=$1
        mkdir -p $SCBI_BDIR/$1
        log=$SCBI_BDIR/$1.log
        (cd $SCBI_BDIR/$1; get-archive $1 $2 $3 2>>$log | tee -a $log; echo "rc=${PIPESTATUS[0]}")
        ;;
    generic)
        mi=()
        get-module-ref mi $3 $2
        m=${mi[0]}
        v=${mi[1]}
        load-module $m
        module=$m
        SCBI_ISOOT=$4
        TVDIR=""
        get-target-dir TVDIR $m $v
        mkdir -p $SCBI_BDIR/$m
        log=$SCBI_BDIR/$m.log
        if [[ $1 == purge ]]; then
            (module-purge $SCBI_BDIR/$m $2 $m $v "$SCBI_TARGET"; echo "rc=$?")
        else
            (cd $SCBI_BDIR/$m; module-$1 $TVDIR/install $2 $m $v "$SCBI_TARGET" "$SCBI_ISOOT" 2>&1 | tee -a $log
             echo "rc=${PIPESTATUS[0]}")
        fi
        ;;
    wrapper)
        mi=()
        get-module-ref mi $2 @root
        m=${mi[0]}
        v=${mi[1]}
        load-module $m
        module=$m
        SCBI_ISOOT=$3
        TVDIR=""
        get-target-dir TVDIR $m $v
        mkdir -p $TVDIR/logs $TVDIR/build $TVDIR/src
        (module-variant-wrapper $TVDIR/install $m $v $1); echo "rc=$?"
        ;;
    check-pkg)
        (check-pkg $1; echo "rc=$?")
        ;;
    pkg-status)
        (r=(); check-pkg-status r $1; echo "${r[*]}")
        ;;
    auto)
        (handle-plan-auto-variant $1)
        ;;
    env)
        load-module $3
        (declare -A SCBI_MODULES_DIR=()
         SCBI_ENV_MODULE=$SCBI_BDIR/env.rec
         rm -f $SCBI_ENV_MODULE
         case $1 in
             env) handle-env $2 $3;;
             build) handle-build-depends-env $2 $3;;
             tests) handle-tests-depends-env $2 $3;;
             *) handle-module-env $2 $3 $1;;
         esac
         echo "rc=$?"
         unset SCBI_ENV_MODULE
         vars=""
         if [[ -f $SCBI_BDIR/env.rec ]]; then
             cat $SCBI_BDIR/env.rec
             vars=$(sed -n 's/^define-var [A-Z]* \([A-Za-z_0-9]*\) .*/\1/p' $SCBI_BDIR/env.rec | sort -u)
         fi
         rm -f $SCBI_BDIR/env.rec
         for k in $(printf '%s\n' "${!SCBI_MODULES_DIR[@]}" | sort); do
             echo "DIR $k=${SCBI_MODULES_DIR[$k]}"
         done
         for v in $vars; do
             echo "VAR $v=${!v}"
         done)
        ;;
esac
}

args=()
for w in "$@"; do
    if [[ $w == @@ ]]; then
        run1 "${args[@]}"
        args=()
    else
        args+=("$w")
    fi
done
[[ ${#args[@]} -gt 0 ]] && run1 "${args[@]}"
exit 0
"""


def out(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main(driver, args):
    argv = words(" ".join(driver.modules))
    b = Builder(driver)
    group: list[str] = []
    for w in argv + ["@@"]:
        if w == "@@":
            if group:
                run1(driver, b, group)
            group = []
        else:
            group.append(w)
    return 0


def probe_env(driver, b, a):
    import os
    import re

    from scbi.bashenv import ShellVars
    from scbi.errors import Exit
    from scbi.steps.modenv import ModuleEnv

    kind, formodule, modref = a[:3]
    Walker(b).load_module(modref)
    #  a sub-shell in the Bash probe
    sv = driver.sv
    driver.sv = ShellVars(dict(sv.values), set(sv.exported), dict(sv.functions))
    saved_dirs = dict(b.modules_dir)
    rec = f"{driver.get('SCBI_BDIR')}/env.rec"
    driver.set("SCBI_ENV_MODULE", rec)
    try:
        if os.path.exists(rec):
            os.unlink(rec)
        me = ModuleEnv(b)
        try:
            if kind == "env":
                rc = me.handle_env(formodule, modref)
            elif kind == "build":
                rc = me.handle_build_depends_env(formodule, modref)
            elif kind == "tests":
                rc = me.handle_tests_depends_env(formodule, modref)
            else:
                me.module_env(formodule, modref, kind)
                rc = 0
        except Exit:
            return
        out(f"rc={rc}")
        names = []
        if os.path.exists(rec):
            text = open(rec).read()
            sys.stdout.write(text)
            names = sorted({m.group(1) for m in re.finditer(r"^define-var [A-Z]* ([A-Za-z_0-9]*) ", text, re.M)})
            os.unlink(rec)
        for k in sorted(b.modules_dir):
            out(f"DIR {k}={b.modules_dir[k]}")
        for v in names:
            out(f"VAR {v}={me.env.get(v)}")
    finally:
        driver.sv = sv
        b.modules_dir = saved_dirs


def run1(driver, b, argv):
    cmd, a = argv[0], argv[1:] + [""] * 3
    if cmd == "env":
        probe_env(driver, b, a)
        return
    if cmd in ("check-pkg", "pkg-status", "auto"):
        from scbi.ospkg import OsPackages

        osp = OsPackages(driver)
        if cmd == "check-pkg":
            out(f"rc={osp.check_pkg(a[0], out)}")
        elif cmd == "pkg-status":
            out(" ".join(osp.check_pkg_status(a[0])))
        else:
            for line in osp.plan_auto_variant(b, a[0]):
                out(line)
        return
    if cmd == "walk":
        rc = Walker(b).walk(a[0], lambda v: out("CB " + " ".join(v)), a[1], "x1", "x2", name="cb")
        out(f"rc={rc}")
        return
    if cmd == "handle-sources":
        import os

        from scbi.sources.handle import Sources

        src = Sources(b, a[0], a[1])
        if driver.registry.load_module(src.module):
            b.load_module(src.module, src.variant)
        mdir = f"{driver.get('SCBI_BDIR')}/{src.module}"
        os.makedirs(mdir, exist_ok=True)
        driver.set("log", f"{driver.get('SCBI_BDIR')}/{src.module}.log")
        cwd = os.getcwd()
        os.chdir(mdir)
        saved = driver.get("DO_UPDATE")
        try:
            for f in ("src", "vcs"):
                if os.path.islink(f):
                    os.unlink(f)
            rc = src.handle()
            out(f"rc={rc} DO_UPDATE={driver.get('DO_UPDATE')}")
        finally:
            #  a sub-shell in the Bash probe
            driver.set("DO_UPDATE", saved)
            os.chdir(cwd)
        return
    if cmd == "get-archive":
        import os

        from scbi.sources.archive.fetch import get_archive

        driver.registry.load_module(a[0])
        mdir = f"{driver.get('SCBI_BDIR')}/{a[0]}"
        os.makedirs(mdir, exist_ok=True)
        log = f"{driver.get('SCBI_BDIR')}/{a[0]}.log"
        cwd = os.getcwd()
        os.chdir(mdir)

        def tee(line):
            out(line)
            with open(log, "a") as f:
                f.write(line + "\n")

        try:
            rc = get_archive(b, a[0], a[1], a[2], log, tee)
        finally:
            os.chdir(cwd)
        out(f"rc={rc}")
        return
    if cmd == "generic":
        import os

        from scbi.steps.generic import Generic

        info = (driver.plan.module_ref(a[2], a[1]) + ["", ""])[:2]
        m, v = info
        if driver.registry.load_module(m):
            b.load_module(m, v)
        saved = {n: driver.get(n) for n in ("SCBI_ISOOT", "module")}
        driver.set("SCBI_ISOOT", a[3])
        driver.set("module", m)
        tvdir = b.target_dir(m, v)
        os.makedirs(f"{driver.get('SCBI_BDIR')}/{m}", exist_ok=True)
        log = f"{driver.get('SCBI_BDIR')}/{m}.log"
        try:
            rc = Generic(b, a[1], m, v, tvdir).step(a[0], None if a[0] == "purge" else log)
        finally:
            for n, val in saved.items():
                driver.set(n, val)
        out(f"rc={rc}")
        return
    if cmd == "wrapper":
        import os

        from scbi.steps.wrapper import StepWrapper

        m, v = (driver.plan.module_ref(a[1]) + ["", ""])[:2]
        if driver.registry.load_module(m):
            b.load_module(m, v)
        saved = {n: driver.get(n) for n in ("SCBI_ISOOT", "module")}
        driver.set("SCBI_ISOOT", a[2])
        driver.set("module", m)
        tvdir = b.target_dir(m, v)
        for sub in ("logs", "build", "src"):
            os.makedirs(f"{tvdir}/{sub}", exist_ok=True)
        try:
            rc = StepWrapper(b, m, v).variant_step(f"{tvdir}/install", a[0])
        finally:
            for n, val in saved.items():
                driver.set(n, val)
        out(f"rc={rc}")
        return
    if cmd == "patch-md5":
        out(buildid.patch_md5(b, a[0]))
        return
    module = a[1] if cmd == "build-id" else a[0]
    info = (driver.plan.module_ref(module) + ["", ""])[:2]
    if driver.registry.load_module(info[0]):
        b.load_module(*info)
    if cmd == "vcs-data":
        r, rc = data.vcs_data(b, a[0], a[1])
        out(f"rc={rc} {' '.join(r)}")
    elif cmd == "archive-data":
        r, rc = data.archive_data(b, a[0], a[1], a[2])
        out(f"rc={rc} {' '.join(r)}")
    elif cmd == "archive-exists":
        out(f"rc={0 if data.archive_exists(b, a[0], a[1], a[2]) else 1}")
    elif cmd == "vcs-dir":
        r, rc = data.vcs_dir(b, a[0])
        out(f"rc={rc} {r}")
    elif cmd == "build-id":
        out("rc=0 " + buildid.build_id(b, driver.get("SCBI_PREFIX"), driver.get("SCBI_TARGET"), a[0], a[1], a[2]))
    elif cmd == "depends-build-id":
        out("rc=0 " + buildid.depends_build_id(b, a[0]))
