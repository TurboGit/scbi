def test(t):
    # echo ========== dmain
    t.runs('./scbi show --depends dmain')

    t.clean_diff("""\
depA
depB
dmain
dmod
oot
""")

    # echo ========== dmain externals
    t.runs('./scbi show --externals:only dmain')

    t.clean_diff("""\
libaws-dev
""")

    # echo ========== dmain modules & externals
    t.runs('./scbi show --externals dmain')

    t.clean_diff("""\
depA
depB
dmain
dmod
libaws-dev
oot
""")

    # echo ========== dmain direct modules & externals
    t.runs('./scbi show --depends:direct --externals dmain')

    t.clean_diff("""\
depA
depB
dmod
libaws-dev
""")
