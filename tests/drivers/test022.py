def test(t):
    # check for enable

    # === not activated
    t.runs('./scbi -f test22')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test22 [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building test22 [default] (n/a)
""")

    # === activated
    t.runs('./scbi -f --enable-light test22')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test22 [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building test22 [default] (n/a)
""")

    t.runs("grep -h '@@@' .root/builds/.logs/*test22*config*")

    t.clean_diff("""\
@@@ LIGHT is not enabled
@@@ LIGHT is enabled
""")
