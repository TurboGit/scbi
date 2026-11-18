def test(t):
    # An interrupted or failed build is redone at the next run, even when
    # the build id is the one of the previous (successful) build: the
    # build id of the sandbox is removed when a build starts and written
    # when it completes. A failing step leaves the sandbox as an
    # interruption does.

    t.set('TVDIR', '.root/builds/rbid/x86_64-linux-gnu-default')

    t.runs('./scbi rbid')
    t.sh('[[ -f $TVDIR/install/bin/rbid ]] && [[ -d $TVDIR/build ]] && [[ ! -L $TVDIR/build ]] && echo ok > $TEST_OUTPUT')
    t.diff("ok\n")

    # =================== out-of-tree changed, failing at config
    t.sh("sed -i 's/^out-of-tree: true$/out-of-tree: false/; s/^config: echo config$/config: false/' "
         "scripts.d/rbid.yaml")
    t.nruns('./scbi rbid')
    t.sh('[[ ! -f $TVDIR/build-id ]] && [[ ! -d $TVDIR/install ]] && echo ok > $TEST_OUTPUT')
    t.diff("ok\n")

    # =================== back to the previous plug-in: rebuilt
    t.sh("sed -i 's/^out-of-tree: false$/out-of-tree: true/; s/^config: false$/config: echo config/' "
         "scripts.d/rbid.yaml")
    t.runs('./scbi rbid')
    t.grep('trigger: not yet built')
    t.ngrep('no build needed')
    t.sh('[[ -f $TVDIR/install/bin/rbid ]] && [[ -d $TVDIR/build ]] && [[ ! -L $TVDIR/build ]] && echo ok > $TEST_OUTPUT')
    t.diff("ok\n")

    # =================== meta-module: a failed (or interrupted) wrapup is
    # run again, the plug-in unchanged
    t.sh('touch .root/builds/rbidmeta-fail')
    t.nruns('./scbi --deps rbidmeta')
    t.grep('wrapup starting')
    t.sh('rm .root/builds/rbidmeta-fail')
    t.runs('./scbi --deps rbidmeta')
    t.grep('wrapup starting')
    t.grep('trigger: not yet built')
    t.runs('./scbi --deps rbidmeta')
    t.ngrep('wrapup starting')
