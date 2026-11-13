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


def run1(driver, b, argv):
    cmd, a = argv[0], argv[1:] + [""] * 3
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
