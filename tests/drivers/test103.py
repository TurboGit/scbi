def test(t):
    t.runs('./scbi show --plan=final1 --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 2 module(s) in the plan
plg1:vz
plg2:vz
""")

    t.runs('./scbi show --plan=final2 --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 2 module(s) in the plan
plg1:vz
plg2:vz
""")
