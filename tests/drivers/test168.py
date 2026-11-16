def test(t):
    #  Test inherit of custom hooks (--custom-hooks): the config hooks call
    #  the inherited ones

    t.runs('./scbi inh-app-hooks')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building inh-app-hooks [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building inh-app-hooks [default] (n/a)
""")

    t.set('LDIR', '.root/builds/inh-app-hooks/build/logs')

    t.runs("grep -h '^@@@' $LDIR/config.log $LDIR/install.log")

    t.diff("""\
@@@ CONFIG
@@@ GENERIC-inh-specific
@@@ SHARED-inh-specific
@@@ INSTALL-inh-specific
""")

    #  --hooks=config --custom-hooks=shared: install not inherited

    t.runs('./scbi inh-app-hooks2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building inh-app-hooks2 [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building inh-app-hooks2 [default] (n/a)
""")

    t.runs("grep -h '^@@@' .root/builds/inh-app-hooks2/build/logs/config.log")

    t.diff("""\
@@@ CONFIG
@@@ SHARED-inh-specific
""")
