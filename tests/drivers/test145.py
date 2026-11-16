def test(t):
    t.runs('./scbi show --build-plan --plan=plgv4')

    t.trim_output()

    t.diff("""\
There is 8 module(s) in the plan
plg1/ng
plg2/ng
plg3/ng:vx
plg4/ng:v1
plg5
plg6/exp
plg7:v1
plg8/new:v1
""")

    t.runs('./scbi show --build-plan=plg8 --plan=plgv4')

    t.trim_output()

    t.diff("""\
There is 8 module(s) in the plan
plg8/new:v1
""")

    t.runs('./scbi show --build-plan:history --plan=plgv4')

    t.trim_output()

    t.diff("""\
There is 8 module(s) in the plan
plg1/ng     plgv4 [plgv1 | plg1]
plg2/ng     plgv4 [plgv1 | exp]
plg3/ng:vx  plgv4 [plgv1 | v1]
plg4/ng:v1  plgv4 [plgv1 | new:v1]
plg5        plgv3
plg6/exp    plgv3
plg7:v1     plgv3
plg8/new:v1 plgv3
""")

    t.runs('./scbi show --build-plan:history=plg1,plg5 --plan=plgv4')

    t.trim_output()

    t.diff("""\
There is 8 module(s) in the plan
plg1/ng plgv4 [plgv1 | plg1]
plg5    plgv3
""")
