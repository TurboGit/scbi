def test(t):
    t.runs('./scbi show --plan=meta --build-plan meta:v5')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 3 module(s) in the plan
m1:v5
m2:v5
meta:v5
""")

    t.runs('./scbi show --plan=meta --build-plan meta')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 3 module(s) in the plan
m1:v2
m2:v2
meta/cc:v2
""")

    t.runs('./scbi show --plan=meta-meta --build-plan meta-meta')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA:1.8
dmod:1.8
meta-meta:1.8
oot:1.8
""")

    t.runs('./scbi show --plan=meta-meta --build-plan depA:9 meta-meta')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA:9
dmod:1.8
meta-meta:1.8
oot:1.8
""")

    t.runs('./scbi show --plan=meta-meta-2 --build-plan meta-meta')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
depA/toto:v9
dmod/x:v9
meta-meta:1.8
oot:v9
""")

    t.runs('./scbi show --plan=meta-meta-3 --build-plan meta-meta-2')

    t.clean_output()
    t.trim_output()

    t.diff("""\
There is 1 module(s) in the plan
meta-meta-2:1.8
""")
