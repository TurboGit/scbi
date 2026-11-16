def test(t):
    t.nruns('./scbi --deps mboggus lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule mboggus [default] setup
xxxx/xx/xx xx:xx:xx : End metamodule mboggus [default] setup

error: missing dependencies for building boggus
error    required by mboggus
error: doesnotexists not found
""")
