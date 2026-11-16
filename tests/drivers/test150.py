def test(t):
    #  Check --clear-cache option

    t.sh("GVER=$(gcc --version | grep gcc | awk '{print $4}')")

    t.runs('./scbi --plan=autov lib1')

    t.sort_output_n_first_lines(6)
    t.trim_output()

    t.diff(t.text("""\
xxxx/xx/xx xx:xx:xx : mainav2=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mainav=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mautov 5 using native variant
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER used

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
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
"""))

    #  No plan rewrite, cache used

    t.runs('./scbi --plan=autov lib1')

    t.trim_output()

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    #  Clear the cache, rewrite is done a first call

    t.runs('./scbi --clear-cache --plan=autov lib1')

    t.sort_output_n_first_lines(6)
    t.trim_output()

    t.diff(t.text("""\
xxxx/xx/xx xx:xx:xx : mainav2=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mainav=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mautov 5 using native variant
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER used

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
"""))
