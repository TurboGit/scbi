def test(t):
    t.set('REP', '$PWD/.root/builds/metaagg/x86_64-linux-gnu-default/install')
    t.set('LDIR', '$PWD/.root/builds/usemetaagg/x86_64-linux-gnu-default/logs')

    t.runs('./scbi metaagg')

    t.clean_diff("""\
2024/03/29 09:56:59 : Metamodule metaagg [default] setup
2024/03/29 09:56:59 : End metamodule metaagg [default] setup

2024/03/29 09:56:59 : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ metaagg
2024/03/29 09:56:59 : native x86_64-linux-gnu
2024/03/29 09:56:59 : steps: setup config build install wrapup
2024/03/29 09:56:59 : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
2024/03/29 09:56:59 : apply patch lib1-0-fix.patch
2024/03/29 09:56:59 : build starting
2024/03/29 09:56:59 : build completed
2024/03/29 09:56:59 : install starting
2024/03/29 09:56:59 : install completed
2024/03/29 09:56:59 : copy install into <sandbox>/install
2024/03/29 09:56:59 : End Building lib1 [default] (master)

2024/03/29 09:56:59 : Building libenv [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ metaagg
2024/03/29 09:56:59 : native x86_64-linux-gnu
2024/03/29 09:56:59 : steps: setup config build install wrapup
2024/03/29 09:57:00 : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
2024/03/29 09:57:00 : config starting
2024/03/29 09:57:00 : config completed
2024/03/29 09:57:00 : build starting
2024/03/29 09:57:00 : build completed
2024/03/29 09:57:00 : install starting
2024/03/29 09:57:00 : install completed
2024/03/29 09:57:00 : copy install into <sandbox>/install
2024/03/29 09:57:00 : End Building libenv [default] (master)

2024/03/29 09:57:00 : Metamodule metaagg [default] wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
2024/03/29 09:57:00 : End metamodule metaagg [default] wrapup
""")

    t.ok('-d $REP')

    t.ok('-f $REP/include/lib1.h')
    t.ok('-f $REP/include/lib2.h')
    t.ok('-f $REP/lib/liblib1.so')
    t.ok('-f $REP/lib/liblib2.so')

    t.runs('./scbi usemetaagg')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building usemetaagg [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building usemetaagg [default] (master)
""")

    t.runs('./scbi --tests:only usemetaagg')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building usemetaagg [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: tests
xxxx/xx/xx xx:xx:xx : tests starting
main on master
liba.C patched version
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : End Building usemetaagg [default] (master)
""")

    #  Check that there is PATH to the aggregate module but not to the
    #  aggregated ones.
    t.grep(*t.words('"/builds/metaagg/" $LDIR/env.cmd'))
    t.ngrep(*t.words('"/builds/lib1/" $LDIR/env.cmd'))
    t.ngrep(*t.words('"/builds/libenv/" $LDIR/env.cmd'))

    t.grep(*t.words('"lib1 git master sha-1 eb90bc4f3" $PWD/.root/builds/metaagg/source-ref'))
    t.grep(*t.words('"libenv git master sha-1 5c345dd4bcb" $PWD/.root/builds/metaagg/source-ref'))
