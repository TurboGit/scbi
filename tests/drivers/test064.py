def test(t):
    t.set('OSHT_STDERR', 'ERROR.TMP')

    t.runs('./scbi hookskindA')

    t.clean_diff("""\
2021/12/19 17:19:38 : Building hookskindA [default] (n/a)
2021/12/19 17:19:38 : native x86_64-linux-gnu
2021/12/19 17:19:38 : steps: setup config build install wrapup
2021/12/19 17:19:38 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
2021/12/19 17:19:38 : default-config starting
2021/12/19 17:19:38 : default-config completed
2021/12/19 17:19:38 : default-build starting
2021/12/19 17:19:38 : default-build completed
2021/12/19 17:19:38 : End Building hookskindA [default] (n/a)
""")

    t.runs('./scbi hookskindA/wxt')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building hookskindA [wxt] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [wxt] starting
xxxx/xx/xx xx:xx:xx : config [wxt] completed
xxxx/xx/xx xx:xx:xx : build [wxt] starting
xxxx/xx/xx xx:xx:xx : build [wxt] completed
xxxx/xx/xx xx:xx:xx : End Building hookskindA [wxt] (n/a)
""")
