def test(t):
    t.runs('./scbi --no-patch lib1')

    # check purge and purge:only
    # ==== no build expected
    t.runs('./scbi --no-patch lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    # ==== purge and re-build
    t.runs('./scbi --no-patch --purge lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Purging lib1 for x86_64-linux-gnu/default

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    # ==== no build expected
    t.runs('./scbi --no-patch lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    # ==== purge:only, no build expected

    t.set('REP', '$PWD/.root/builds/lib1')

    # OK build directory present before purge
    t.ok('-h $REP/x86_64-linux-gnu-default/build')

    t.runs('./scbi --purge:only lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Purging lib1 for x86_64-linux-gnu/default
""")

    # OK build directory removed, only manifest + logs found
    t.set('FILES', '"$(ls $REP/x86_64-linux-gnu-default | sort | tr \'\\n\' \' \')"')
    t.set('FILES', '"${FILES:0:-1}"')

    t.is_('"$FILES"', '==', '"logs manifest"')

    t.unset('REP')

    # ==== re-build after purge
    t.runs('./scbi --no-patch lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")
