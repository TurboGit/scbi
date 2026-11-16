def test(t):
    t.nruns('./scbi --deps depslibdeps')

    t.clean_diff("""\
error: missing dependencies for building libdeps
error    required by depslibdeps
error: unknown-lib not found
""")

    t.nruns('./scbi --deps Mdepslibdeps')

    t.clean_diff("""\
error: missing dependencies for building libdeps
error    required by depslibdeps
error    required by Mdepslibdeps
error: unknown-lib not found
""")

    t.nruns('./scbi --plan=deps --deps Mdepslibdeps')

    t.clean_diff("""\
error: missing dependencies for building libdeps/gothere
error    required by depslibdeps/here:dev
error    required by Mdepslibdeps/go:v9
error: unknown-lib not found
""")

    t.nruns('./scbi --plan=deps --deps Mdepslibdeps/next')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ Mdepslibdeps/next
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : apply patch lib1-0-fix.patch
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)

error: missing dependencies for building libdeps/gothere
error    required by depslibdeps/here:dev
error    required by Mdepslibdeps/next
error: unknown-lib not found
""")
