def test(t):
    t.set('REP', '$PWD/.root/builds')
    t.set('ADIR', '$REP/metaagg4')
    t.set('MDIR', '$ADIR/x86_64-linux-gnu-default/install')

    t.runs('./scbi --deps metaagg4')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule metaagg4 [default] setup
xxxx/xx/xx xx:xx:xx : End metamodule metaagg4 [default] setup

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ mainlib
xxxx/xx/xx xx:xx:xx :   ↳ metaagg4
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
xxxx/xx/xx xx:xx:xx :   ↳ metaagg4
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

xxxx/xx/xx xx:xx:xx : Metamodule metaagg4 [default] wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End metamodule metaagg4 [default] wrapup
""")

    t.ok('-d $REP/install')
    t.ok('-d $REP/lib1')
    t.ok('-d $REP/mainlib')
    t.ok('-d $REP/metaagg4')
    t.ok('-f $MDIR/bin/mainlib')
    t.ok('-f $MDIR/lib/liblib1.so')
    t.ok('-f $MDIR/include/lib1.h')

    t.ngrep(*t.words('"^metaagg " $ADIR/source-ref'))
    t.grep(*t.words('"^mainlib " $ADIR/source-ref'))
    t.grep(*t.words('"^lib1 " $ADIR/source-ref'))
