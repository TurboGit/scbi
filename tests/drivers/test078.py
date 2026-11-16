def test(t):
    t.sh("GVER=$(gcc --version | grep gcc | awk '{print $4}')")

    #  Check auto variant with a for-module

    t.runs('./scbi --plan=autov --deps mautov')

    t.sort_output_n_first_lines(6)

    t.clean_diff(t.text("""\
xxxx/xx/xx xx:xx:xx : mainav2=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mainav=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mautov 5 using native variant
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER used

xxxx/xx/xx xx:xx:xx : Building mautov [native] ($GVER)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building mautov [native] ($GVER)
"""))

    t.ok('-d .root/builds/mautov/x86_64-linux-gnu-native')
    t.nok('-d .root/builds/mautov/x86_64-linux-gnu-mainav')
    t.nok('-d .root/builds/mautov/x86_64-linux-gnu-for2')

    t.runs('./scbi --plan=autov --deps mainav')

    t.sort_output_n_first_lines(6)

    t.clean_diff(t.text("""\
xxxx/xx/xx xx:xx:xx : mainav2=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mainav=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mautov 5 using native variant
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER used

xxxx/xx/xx xx:xx:xx : Building mautov [mainav] (99.99)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ mainav
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [mainav] starting
xxxx/xx/xx xx:xx:xx : config [mainav] completed
xxxx/xx/xx xx:xx:xx : build [mainav] starting
xxxx/xx/xx xx:xx:xx : build [mainav] completed
xxxx/xx/xx xx:xx:xx : install [mainav] starting
xxxx/xx/xx xx:xx:xx : install [mainav] completed
xxxx/xx/xx xx:xx:xx : End Building mautov [mainav] (99.99)

xxxx/xx/xx xx:xx:xx : Building mainav [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building mainav [default] (n/a)
"""))

    t.ok('-d .root/builds/mautov/x86_64-linux-gnu-native')
    t.ok('-d .root/builds/mautov/x86_64-linux-gnu-mainav')
    t.nok('-d .root/builds/mautov/x86_64-linux-gnu-for2')

    t.runs('./scbi --plan=autov --deps mainav2')

    t.sort_output_n_first_lines(6)

    t.clean_diff(t.text("""\
xxxx/xx/xx xx:xx:xx : mainav2=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mainav=mautov 99.99 using standard variant
xxxx/xx/xx xx:xx:xx : mautov 5 using native variant
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER used

xxxx/xx/xx xx:xx:xx : Building mautov [for2] (99.99)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ mainav2
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [for2] starting
xxxx/xx/xx xx:xx:xx : config [for2] completed
xxxx/xx/xx xx:xx:xx : build [for2] starting
xxxx/xx/xx xx:xx:xx : build [for2] completed
xxxx/xx/xx xx:xx:xx : install [for2] starting
xxxx/xx/xx xx:xx:xx : install [for2] completed
xxxx/xx/xx xx:xx:xx : End Building mautov [for2] (99.99)

xxxx/xx/xx xx:xx:xx : Building mainav2 [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building mainav2 [default] (n/a)
"""))

    t.ok('-d .root/builds/mautov/x86_64-linux-gnu-native')
    t.ok('-d .root/builds/mautov/x86_64-linux-gnu-mainav')
    t.ok('-d .root/builds/mautov/x86_64-linux-gnu-for2')
