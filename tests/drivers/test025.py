def test(t):
    # check that we properly rebuild and install cleanly

    t.set('REP', '$PWD/.root/builds/oot2')

    t.sh('rm -fr $REP')

    # ========== build 1 oot2
    t.runs('./scbi oot2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building oot2 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building oot2 [default] (master)
""")

    t.sh("""\
echo some text > $REP/build/install/i-some-file
echo some text > $REP/build/build/b-some-file
""")

    # ========== build 2 oot2
    t.runs('./scbi -f oot2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building oot2 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building oot2 [default] (master)
""")

    t.nok('-f $REP/build/install/i-some-file')
    t.ok('-f $REP/build/build/b-some-file')

    # ========== build 3 oot2
    t.runs('./scbi -f --safe oot2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building oot2 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building oot2 [default] (master)
""")

    t.nok('-f $REP/build/build/b-some-file')

    # ========== build 4 oot2

    t.runs('./scbi -f oot2/no')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building oot2 [no] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : build [no] starting
xxxx/xx/xx xx:xx:xx : build [no] completed
xxxx/xx/xx xx:xx:xx : install [no] starting
xxxx/xx/xx xx:xx:xx : install [no] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building oot2 [no] (master)
""")

    t.sh("""\
rm -f $REP/build/src/b-some-file
echo some text > $REP/build/build/b-some-file
""")

    t.ok('-f $REP/build/src/b-some-file')

    t.unset('REP')
