def test(t):
    #  the drivers of the cache use one
    t.set("SCBI_CACHE_DIR", "$ROOTDIR/.root/.cache")

    t.runs('./scbi crossmod')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building crossmod [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building crossmod [default] (n/a)
""")

    t.runs('./scbi --target=x86_64-pc-mingw32 crossmod')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building crossmod [default] (n/a)
xxxx/xx/xx xx:xx:xx : cross x86_64-pc-mingw32
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building crossmod [default] (n/a)
""")
