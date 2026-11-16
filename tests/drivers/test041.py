def test(t):
    # test for the native variants (with-variants): the default variant builds,
    # the native one runs no step and depends on the given modules

    t.runs('./scbi natv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building natv [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building natv [default] (n/a)
""")

    t.grep('define-var SET NATV_ENV "env"', '.root/builds/natv/build/logs/env.cmd')

    t.runs('./scbi natv/native')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building natv [native] (os)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
error: libA not found
error: libB not found
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building natv [native] (os)
""")
