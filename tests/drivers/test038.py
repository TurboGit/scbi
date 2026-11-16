def test(t):
    t.nruns('./scbi --deps boggus lib1')

    t.diff("""\
error: missing dependencies for building boggus
error: doesnotexists not found
""")
