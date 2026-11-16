def test(t):
    # check for --warning:external

    t.nruns('./scbi --deps libdeps')

    t.clean_diff("""\
error: missing dependencies for building libdeps
error: unknown-lib not found
""")

    t.runs('./scbi --deps:warning libdeps')

    t.clean_diff("""\
warning: missing dependencies for building libdeps
warning: unknown-lib not found
xxxx/xx/xx xx:xx:xx : Building libdeps [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
warning: unknown-lib not found
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building libdeps [default] (master)
""")
