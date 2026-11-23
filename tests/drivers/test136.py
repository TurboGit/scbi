def test(t):
    # Check for flat directory suppoer (--flat)

    t.runs('./scbi --flat --deps mainlib/depdir')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ mainlib/depdir
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

xxxx/xx/xx xx:xx:xx : Building mainlib [depdir] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : depdir-post-setup starting
xxxx/xx/xx xx:xx:xx : depdir-post-setup completed
xxxx/xx/xx xx:xx:xx : build [depdir] starting
xxxx/xx/xx xx:xx:xx : build [depdir] completed
xxxx/xx/xx xx:xx:xx : install [depdir] starting
xxxx/xx/xx xx:xx:xx : install [depdir] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building mainlib [depdir] (master)
""")

    t.set('BDIR', '.root/builds')

    t.sh("""\
SCBI_HOST=$(gcc -dumpmachine | sed -e 's/-pc//;s/-unknown//')
SCBI_TARGET=$SCBI_HOST
""")

    t.ok('-h $BDIR/mainlib/$SCBI_TARGET-depdir')
    t.ok('-d $BDIR/mainlib/$SCBI_TARGET-depdir')
    t.ok('-h $BDIR/lib1/$SCBI_TARGET-default')

    t.ok('-d $BDIR/1/logs')
    t.ok('-d $BDIR/1/install')
    t.ok('-d $BDIR/1/src')
    t.ok('-f $BDIR/1/manifest')
    t.ok('-f $BDIR/mainlib/build/manifest')
    t.grep(*t.words('mainlib $BDIR/1/manifest'))

    t.sh('LIB1DIR=$(realpath $BDIR/lib1/$SCBI_TARGET-default)')

    t.ok('-d $LIB1DIR')
    t.ok('-d $BDIR/2/logs')
    t.ok('-d $BDIR/2/install')
    t.ok('-d $BDIR/2/src')
    t.ok('-f $BDIR/2/manifest')
    t.ok('-f $BDIR/lib1/build/manifest')
    t.grep(*t.words('lib1.h $BDIR/2/manifest'))

    t.set('LFILE', '.root/builds/.logs/x*depdir-post-setup.log')

    t.grep(*t.words('"^@@@LIB1-INS ${LIB1DIR}/install" $LFILE'))
    t.grep(*t.words('"^@@@LIB1-SRC ${LIB1DIR}/src" $LFILE'))
    t.grep(*t.words('"^@@@LIB1-BLD ${LIB1DIR}/src" $LFILE'))
    t.grep(*t.words('"^@@@LIB1-FINS ${LIB1DIR}/install" $LFILE'))
    t.grep(*t.words('"^@@@LIB1-FSRC ${LIB1DIR}/src" $LFILE'))
    t.grep(*t.words('"^@@@LIB1-FBLD ${LIB1DIR}/src" $LFILE'))
    #  a value hook (config-options) sees the module directories too
    t.grep(*t.words('"^@@@LIB1-OPT --lib1=${LIB1DIR}/install" $LFILE'))

    t.ok('-d $BDIR/install/bin')
    t.ok('-d $BDIR/install/include')
    t.ok('-d $BDIR/install/lib')
    t.ok('-f $BDIR/install/bin/mainlib')
    t.ok('-f $BDIR/install/include/lib1.h')

    #  Check proper clean-up when switch to/from flat mode

    t.runs('./scbi --deps mainlib/depdir')

    t.set('LIB1DIR', '$BDIR/lib1/$SCBI_TARGET-default')

    t.ok('-d $LIB1DIR')
    t.nok('-h $LIB1DIR')
    t.nok('-d $BDIR/1')
    t.nok('-d $BDIR/2')

    t.runs('./scbi --deps --flat mainlib/depdir')

    t.ok('-d $LIB1DIR')
    t.ok('-h $LIB1DIR')
    t.ok('-d $BDIR/1')
    t.ok('-d $BDIR/2')
