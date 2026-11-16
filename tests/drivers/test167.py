def test(t):
    t.runs('./scbi show --rdepends usethisplg')

    t.clean_diff("""\
utp1
utp2 (build)
utp3 [test]
utp4
utp5 [utp]
utp6 (modules)
""")
