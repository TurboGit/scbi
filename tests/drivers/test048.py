def test(t):
    # check for depends & call-variant-hooks

    #no variant
    t.runs('./scbi --log:yes --deps dephook')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building depA [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ dephook
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
depA
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building depA [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building dephook [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
call -DOnlyCommon
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building dephook [default] (n/a)
""")

    #variant vara
    t.runs('./scbi --log:yes --deps dephook/vara')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building depA [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ dephook/vara
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building depA [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building dephook [vara] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [vara] starting
call -DOnlyCommon -DA=yes
xxxx/xx/xx xx:xx:xx : config [vara] completed
xxxx/xx/xx xx:xx:xx : End Building dephook [vara] (n/a)
""")

    #variant varb
    t.runs('./scbi --log:yes --deps dephook/varb')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building depA [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ dephook/varb
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building depA [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building depB [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ dephook/varb
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
depB
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building depB [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building dephook [varb] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [varb] starting
call -DOnlyCommon
xxxx/xx/xx xx:xx:xx : config [varb] completed
xxxx/xx/xx xx:xx:xx : End Building dephook [varb] (n/a)
""")

    #variant vara and varb
    t.runs('./scbi --log:yes --deps dephook/vara.varb')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building depA [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ dephook/vara.varb
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building depA [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building depB [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ dephook/vara.varb
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building depB [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building dephook [vara varb] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [vara varb] starting
call -DOnlyCommon -DA=yes
xxxx/xx/xx xx:xx:xx : config [vara varb] completed
xxxx/xx/xx xx:xx:xx : End Building dephook [vara varb] (n/a)
""")
