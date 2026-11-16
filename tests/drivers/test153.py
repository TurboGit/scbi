def test(t):
    t.runs('./scbi --plan=as lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [variant-no-patch] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [variant-no-patch] (v1)
""")

    t.runs('./scbi --plan=as/a lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [variant-no-patch] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [variant-no-patch] (master)
""")

    t.runs('./scbi --no-patch --plan=as/b lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v1)
""")

    t.nruns('./scbi --plan=as/wrong lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : build (FAILED) donotexist has no reference in build plan
""")

    t.runs('./scbi --plan=as/skip lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Module lib1 marked to be skipped
""")
