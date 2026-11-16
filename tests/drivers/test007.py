def test(t):
    # check that we properly rebuild/install variants
    # ========== build/install lib2

    t.set('DIR', '$PWD/.root/builds/lib2/build')

    t.nok('-f $DIR/logs/env.cmd')

    t.runs('./scbi --tests lib2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib2 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
libb.B master (default)
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [default] (master)
""")

    t.ok('-f $DIR/logs/env.cmd')

    t.grep(*t.words('SCBI_MODULES_DIR $DIR/logs/env.cmd'))
    t.grep(*t.words("'\\-default' $DIR/logs/env.cmd"))
    t.ngrep(*t.words("'\\-variant1' $DIR/logs/env.cmd"))

    # ========== build/install lib2/variant
    t.runs('./scbi --tests lib2/variant1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib2 [variant1] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : variant1-config starting
xxxx/xx/xx xx:xx:xx : variant1-config completed
xxxx/xx/xx xx:xx:xx : build [variant1] starting
xxxx/xx/xx xx:xx:xx : build [variant1] completed
xxxx/xx/xx xx:xx:xx : install [variant1] starting
xxxx/xx/xx xx:xx:xx : install [variant1] completed
xxxx/xx/xx xx:xx:xx : tests [variant1] starting
main
libb.B master (variant1)
xxxx/xx/xx xx:xx:xx : tests [variant1] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [variant1] (master)
""")

    # ========== install lib2
    t.runs('./scbi --tests lib2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib2 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : tests starting
main
libb.B master (default)
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [default] (master)
""")

    # ========== build/install lib2/variant v2
    t.runs('./scbi --tests lib2/variant1:v2.0')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib2 [variant1] (v2.0)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : variant1-config starting
xxxx/xx/xx xx:xx:xx : variant1-config completed
xxxx/xx/xx xx:xx:xx : build [variant1] starting
xxxx/xx/xx xx:xx:xx : build [variant1] completed
xxxx/xx/xx xx:xx:xx : install [variant1] starting
xxxx/xx/xx xx:xx:xx : install [variant1] completed
xxxx/xx/xx xx:xx:xx : tests [variant1] starting
main
libb.B v2 (variant1)
xxxx/xx/xx xx:xx:xx : tests [variant1] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [variant1] (v2.0)
""")

    # ========== build/install lib2/variant tag v1.0.0
    t.runs('./scbi --tests lib2/variant1:v1.0.0')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib2 [variant1] (v1.0.0)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : variant1-config starting
xxxx/xx/xx xx:xx:xx : variant1-config completed
xxxx/xx/xx xx:xx:xx : build [variant1] starting
xxxx/xx/xx xx:xx:xx : build [variant1] completed
xxxx/xx/xx xx:xx:xx : install [variant1] starting
xxxx/xx/xx xx:xx:xx : install [variant1] completed
xxxx/xx/xx xx:xx:xx : tests [variant1] starting
main
libb.A master (variant1)
xxxx/xx/xx xx:xx:xx : tests [variant1] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [variant1] (v1.0.0)
""")

    # ========== just test lib2/variant tag v1.0.0
    t.runs('./scbi --tests lib2/variant1:v1.0.0')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

xxxx/xx/xx xx:xx:xx : Building lib2 [variant1] (v1.0.0)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : tests [variant1] starting
main
libb.A master (variant1)
xxxx/xx/xx xx:xx:xx : tests [variant1] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [variant1] (v1.0.0)
""")

    t.ok('-f $DIR/logs/env.cmd')

    t.grep(*t.words('SCBI_MODULES_DIR $DIR/logs/env.cmd'))
    t.ngrep(*t.words("'\\-default' $DIR/logs/env.cmd"))
    t.grep(*t.words("'\\-variant1' $DIR/logs/env.cmd"))
