def test(t):
    t.runs('./scbi show --plan=modver/meta --build-plan')

    t.clean_diff("""\
There is 3 module(s) in the plan
liba:#12
libb:#12
meta-mod-ver:#12
""")

    t.runs('./scbi show --plan=modver/la --build-plan')

    t.clean_diff("""\
There is 3 module(s) in the plan
liba:#17
libb:#12
meta-mod-ver:#12
""")
