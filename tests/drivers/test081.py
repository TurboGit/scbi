def test(t):
    # check that external env is properly trigerring a rebuild

    ###### should build

    t.runs('./scbi extenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building extenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building extenv [default] (master)
""")

    ###### no build

    t.runs('./scbi extenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building extenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building extenv [default] (master)
""")

    ###### should build since EXTENV_VAR is set

    t.set('EXTENV_VAR', '"one"')

    t.runs('./scbi extenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building extenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building extenv [default] (master)
""")

    ###### no build EXTENV_VAR unchanged

    t.runs('./scbi extenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building extenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building extenv [default] (master)
""")

    ###### should build since EXTENV_VAR is changed

    t.set('EXTENV_VAR', '"two"')

    t.runs('./scbi extenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building extenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building extenv [default] (master)
""")

    ###### should build again since EXTENV_VAR is changed

    t.set('EXTENV_VAR', '"three"')

    t.runs('./scbi extenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building extenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building extenv [default] (master)
""")

    ###### no build EXTENV_VAR unchanged

    t.runs('./scbi extenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building extenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building extenv [default] (master)
""")
