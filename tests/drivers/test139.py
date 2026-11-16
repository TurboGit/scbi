def test(t):
    t.runs('./scbi show --depends --externals:only cdb')

    t.no_output_version()

    t.clean_diff("""\
make:x.x
""")
