def test(t):
    # check for super-module without deps (only setup & wrapup)
    #

    t.runs('./scbi --purge:only lib1')
    t.runs('./scbi --purge:only lib2')

    # echo ========== build supermod
    t.runs('./scbi --no-patch supermod')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule supermod [default] setup
xxxx/xx/xx xx:xx:xx : setup starting
xxxx/xx/xx xx:xx:xx : setup completed
xxxx/xx/xx xx:xx:xx : End metamodule supermod [default] setup

xxxx/xx/xx xx:xx:xx : Metamodule supermod [default] wrapup
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : End metamodule supermod [default] wrapup
""")
