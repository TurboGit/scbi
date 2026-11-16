def test(t):
    t.runs('./scbi test18')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test18 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building test18 [default] (master)
""")

    t.runs('./scbi test18/alt')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test18 [alt] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [alt] starting
xxxx/xx/xx xx:xx:xx : config [alt] completed
xxxx/xx/xx xx:xx:xx : build [alt] starting
xxxx/xx/xx xx:xx:xx : build [alt] completed
xxxx/xx/xx xx:xx:xx : install [alt] starting
xxxx/xx/xx xx:xx:xx : install [alt] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/local-install
xxxx/xx/xx xx:xx:xx : End Building test18 [alt] (master)
""")
