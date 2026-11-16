def test(t):
    t.runs('./scbi show --depends cd1')

    t.diff("""\
cd1
cd2
cd3
cdb
""")
