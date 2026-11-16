def test(t):
    t.nruns('./scbi --unknown-options')

    t.diff("""\
getopt: unrecognized option '--unknown-options'
try "scbi --help" for more information.
""")

    t.nruns('./scbi -P')

    t.diff("""\
getopt: invalid option -- 'P'
try "scbi --help" for more information.
""")

    t.nruns('./scbi --ukw lib1')

    t.diff("""\
getopt: unrecognized option '--ukw'
try "scbi --help" for more information.
""")
