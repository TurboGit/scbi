def test(t):
    # Check for auto variant

    t.runs('./scbi lib1')

    # =============== A AUTO on command line - no native
    t.nruns('./scbi autovarA/auto')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : autovarA (FAILED) autovarA auto mode must define a native variant
""")

    # =============== A AUTO on plan - no native
    t.nruns('./scbi --plan=autoa autovarA')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : autovarA (FAILED) autovarA auto mode must define a native variant
""")

    # =============== B AUTO on command line
    t.runs('./scbi autovarB/auto')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : autovarB using standard variant
xxxx/xx/xx xx:xx:xx :   ↳ squid-cgi v.vv not installed

xxxx/xx/xx xx:xx:xx : Building autovarB [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building autovarB [default] (n/a)
""")

    # =============== B AUTO on plan
    t.runs('./scbi --plan=autob autovarB')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : autovarB using standard variant
xxxx/xx/xx xx:xx:xx :   ↳ squid-cgi v.vv not installed

xxxx/xx/xx xx:xx:xx : Building autovarB [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building autovarB [default] (n/a)
""")

    # =============== C AUTO on command line
    t.runs('./scbi autovarC/auto')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : autovarC using standard variant
xxxx/xx/xx xx:xx:xx :   ↳ unknown dependency shouldnotexist-dev

xxxx/xx/xx xx:xx:xx : Building autovarC [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building autovarC [default] (n/a)
""")
