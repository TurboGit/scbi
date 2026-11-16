def test(t):
    # check for dry-run

    # just mainlib:
    t.runs('./scbi --dry-run mainlib')

    t.clean_diff("""\
mainlib
""")

    # mainlib and deps:
    t.runs('./scbi --dry-run --deps mainlib')

    t.clean_diff("""\
lib1
mainlib
""")
