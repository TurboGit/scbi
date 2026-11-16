def test(t):
    t.runs('./scbi --plan=skipforce lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Module lib1 marked to be skipped
""")

    t.runs('./scbi --plan=skipforce lib1:force')

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

    t.runs('./scbi --plan=skipforceg lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Module lib1 marked to be skipped
""")

    t.runs('./scbi --plan=skipforceg lib1:force')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [variant-no-patch] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [variant-no-patch] (v1)
""")

    t.nruns('./scbi --plan=skipforcefor --deps mainlib')

    t.runs('./scbi --plan=skipforcefor mainlib=lib1:force --deps mainlib')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [variant-no-patch] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [variant-no-patch] (v1)

xxxx/xx/xx xx:xx:xx : Building mainlib [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building mainlib [default] (master)
""")

    #  Delete lib1 & mainlib to ensure recompilation later

    t.sh('./scbi --quiet --plan=skipforceuse --purge:only --deps lib1:force mainlib')

    t.nruns('./scbi --plan=skipforceuse --deps mainlib')

    t.runs('./scbi --plan=skipforceuse lib1:force --deps mainlib')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

xxxx/xx/xx xx:xx:xx : Building lib1 [variant-no-patch] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [variant-no-patch] (v1)

xxxx/xx/xx xx:xx:xx : Building mainlib [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building mainlib [default] (master)
""")
