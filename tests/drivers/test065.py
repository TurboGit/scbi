def test(t):
    # Build v1

    t.runs('./scbi modver:v1')

    t.clean_diff("""\
2021/12/21 14:05:45 : Building modver [default] (v1)
2021/12/21 14:05:45 : native x86_64-linux-gnu
2021/12/21 14:05:45 : steps: setup config build install wrapup
2021/12/21 14:05:45 : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
2021/12/21 14:05:45 : config starting
2021/12/21 14:05:45 : config completed
2021/12/21 14:05:45 : build starting
2021/12/21 14:05:45 : build completed
2021/12/21 14:05:45 : install starting
2021/12/21 14:05:45 : install completed
2021/12/21 14:05:45 : End Building modver [default] (v1)
""")

    # Build v1 again, no build all matches

    t.runs('./scbi modver:v1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

2021/12/21 14:05:45 : Building modver [default] (v1)
2021/12/21 14:05:45 : native x86_64-linux-gnu
2021/12/21 14:05:45 : steps: setup config build install wrapup
2021/12/21 14:05:45 : no build needed: versions matching
2021/12/21 14:05:45 : End Building modver [default] (v1)
""")

    # Build v2

    t.runs('./scbi modver:v2')

    t.clean_diff("""\
2021/12/21 14:05:45 : Building modver [default] (v2)
2021/12/21 14:05:45 : native x86_64-linux-gnu
2021/12/21 14:05:45 : steps: setup config build install wrapup
2021/12/21 14:05:46 : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
2021/12/21 14:05:46 : config starting
2021/12/21 14:05:46 : config completed
2021/12/21 14:05:46 : build starting
2021/12/21 14:05:46 : build completed
2021/12/21 14:05:46 : install starting
2021/12/21 14:05:46 : install completed
2021/12/21 14:05:46 : End Building modver [default] (v2)
""")

    # Build v2 variant var

    t.runs('./scbi modver/var:v2')

    t.clean_diff("""\
2021/12/21 14:05:46 : Building modver [var] (v2)
2021/12/21 14:05:46 : native x86_64-linux-gnu
2021/12/21 14:05:46 : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: versions not matching
2021/12/21 14:05:46 : config [var] starting
2021/12/21 14:05:46 : config [var] completed
2021/12/21 14:05:46 : build [var] starting
2021/12/21 14:05:46 : build [var] completed
2021/12/21 14:05:46 : install [var] starting
2021/12/21 14:05:46 : install [var] completed
2021/12/21 14:05:46 : End Building modver [var] (v2)
""")

    # Build v2 variant var again, the build is done again as the version
    # of the module is reported as 0.5 whereas the requested version is 2.

    t.runs('./scbi modver/var:v2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

2021/12/21 14:05:46 : Building modver [var] (v2)
2021/12/21 14:05:46 : native x86_64-linux-gnu
2021/12/21 14:05:46 : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: versions not matching
2021/12/21 14:05:47 : config [var] starting
2021/12/21 14:05:47 : config [var] completed
2021/12/21 14:05:47 : build [var] starting
2021/12/21 14:05:47 : build [var] completed
2021/12/21 14:05:47 : install [var] starting
2021/12/21 14:05:47 : install [var] completed
2021/12/21 14:05:47 : End Building modver [var] (v2)
""")

    # Build master

    t.runs('./scbi modver')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building modver [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building modver [default] (master)
""")

    t.runs('./scbi modver')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building modver [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building modver [default] (master)
""")
