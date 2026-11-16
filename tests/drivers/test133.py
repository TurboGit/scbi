def test(t):
    #  Check that we take only the first variant

    t.set('LDIR', '.root/builds/pmorph/build/logs')

    t.runs('./scbi pmorph/a.b')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building pmorph [a b] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : a-config [a b] starting
xxxx/xx/xx xx:xx:xx : a-config [a b] completed
xxxx/xx/xx xx:xx:xx : End Building pmorph [a b] (n/a)
""")

    t.grep(*t.words('"CONFIG a" $LDIR/*config.log'))

    t.runs('./scbi pmorph/b.a')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building pmorph [b a] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : b-config [b a] starting
xxxx/xx/xx xx:xx:xx : b-config [b a] completed
xxxx/xx/xx xx:xx:xx : End Building pmorph [b a] (n/a)
""")

    t.grep(*t.words('"CONFIG b" $LDIR/*config.log'))

    t.runs('./scbi pmorph')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building pmorph [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : default-config starting
xxxx/xx/xx xx:xx:xx : default-config completed
xxxx/xx/xx xx:xx:xx : End Building pmorph [default] (n/a)
""")

    t.grep(*t.words('"CONFIG default" $LDIR/*config.log'))

    t.runs('./scbi pmorph/z')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building pmorph [z] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [z] starting
xxxx/xx/xx xx:xx:xx : config [z] completed
xxxx/xx/xx xx:xx:xx : End Building pmorph [z] (n/a)
""")

    t.grep(*t.words('"CONFIG (none)" $LDIR/*config.log'))

    t.runs('./scbi pmorph/z.a')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building pmorph [z a] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : a-config [z a] starting
xxxx/xx/xx xx:xx:xx : a-config [z a] completed
xxxx/xx/xx xx:xx:xx : End Building pmorph [z a] (n/a)
""")

    t.grep(*t.words('"CONFIG a" $LDIR/*config.log'))
