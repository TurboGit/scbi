def test(t):
    # check that patches are properly applied if present

    # echo ========== lib1 patched version
    t.runs('./scbi --tests lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : apply patch lib1-0-fix.patch
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.C patched version
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    # echo ========== lib1 standard version
    t.runs('./scbi --tests --no-patch lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.C master
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    # echo ========== lib1 patched again
    t.runs('./scbi --tests lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : apply patch lib1-0-fix.patch
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.C patched version
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    # echo ========== lib1 variant no patch
    t.runs('./scbi --tests lib1/variant-no-patch')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [variant-no-patch] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : build [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] starting
xxxx/xx/xx xx:xx:xx : install [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : tests [variant-no-patch] starting
main
liba.C master
xxxx/xx/xx xx:xx:xx : tests [variant-no-patch] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [variant-no-patch] (master)
""")
