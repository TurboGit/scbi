def test(t):
    t.runs('./scbi show --target=i686-pc-mingw32 --plan=cross --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
modA/cross
modB/targeti686
modC/targetmingw32
modD
""")

    t.runs('./scbi show --target=x86_64-pc-mingw32 --plan=cross --build-plan lib1')

    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
modA/cross
modB
modC/targetmingw32
modD
""")
