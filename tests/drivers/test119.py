def test(t):
    t.set('REP', '$PWD/.root/builds')
    t.set('MDIR', '$REP/metaagg3/x86_64-linux-gnu-agg/install')

    t.runs('./scbi --deps metaagg3/agg')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule metaagg3 [agg] setup
xxxx/xx/xx xx:xx:xx : End metamodule metaagg3 [agg] setup

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ mainlib
xxxx/xx/xx xx:xx:xx :   ↳ metaagg3/agg
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : apply patch lib1-0-fix.patch
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)

xxxx/xx/xx xx:xx:xx : Building mainlib [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ metaagg3/agg
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building mainlib [default] (master)

xxxx/xx/xx xx:xx:xx : Metamodule metaagg3 [agg] wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End metamodule metaagg3 [agg] wrapup
""")

    t.ok('-d $REP/install')
    t.ok('-d $REP/lib1')
    t.ok('-d $REP/mainlib')
    t.ok('-d $REP/metaagg3')
    t.ok('-f $MDIR/bin/mainlib')
    t.nok('-f $MDIR/include')

    t.runs('./scbi shell --run="which mainlib ; mainlib" metaagg3/agg')

    t.clean_diff("""\
<pwd>/.root/builds/metaagg3/x86_64-linux-gnu-agg/install/bin/mainlib
main on master
liba.C patched version
""")

    t.runs('./scbi shell --run="which mainlib ; mainlib" metaagg3')

    t.clean_diff("""\
<pwd>/.root/builds/mainlib/x86_64-linux-gnu-default/install/bin/mainlib
main on master
liba.C patched version
""")
