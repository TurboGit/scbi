def test(t):
    # check for config-options special hooks

    # no variant
    t.runs('./scbi --log:yes confopts')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building confopts [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
call -DcommonX -DcommonY
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building confopts [default] (n/a)
""")

    # variant vara
    t.runs('./scbi --log:yes confopts/vara')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building confopts [vara] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [vara] starting
call -DcommonX -DcommonY -DvaraA
xxxx/xx/xx xx:xx:xx : config [vara] completed
xxxx/xx/xx xx:xx:xx : End Building confopts [vara] (n/a)
""")

    # variant varb
    t.runs('./scbi --log:yes confopts/varb')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building confopts [varb] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [varb] starting
call -DcommonX -DcommonY -DvarbA -DvarbB
xxxx/xx/xx xx:xx:xx : config [varb] completed
xxxx/xx/xx xx:xx:xx : End Building confopts [varb] (n/a)
""")

    # variant vara and varb
    t.runs('./scbi --log:yes confopts/vara.varb')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building confopts [vara varb] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [vara varb] starting
call -DcommonX -DcommonY -DvaraA -DvarbA -DvarbB
xxxx/xx/xx xx:xx:xx : config [vara varb] completed
xxxx/xx/xx xx:xx:xx : End Building confopts [vara varb] (n/a)
""")
