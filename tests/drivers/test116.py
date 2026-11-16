def test(t):
    t.runs('./scbi shell --run="echo toto" dorun')

    t.diff("""\
toto
""")

    t.runs('./scbi shell --run dorun')

    t.diff("""\
dorun
default
""")

    t.runs('./scbi shell --run dorun/one')

    t.diff("""\
dorun
one
""")

    t.runs('./scbi shell --run dorun/one.two')

    t.diff("""\
dorun
one
two
""")

    t.runs('./scbi shell --run dorun/two.one')

    t.diff("""\
dorun
two
one
""")
