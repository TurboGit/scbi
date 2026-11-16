def test(t):
    t.nruns('./scbi plgwronghook:#v9')

    t.clean_diff("""\
2023/07/27 11:17:04 : Building plgwronghook [default] (v9)
2023/07/27 11:17:04 : native x86_64-linux-gnu
2023/07/27 11:17:04 : steps: setup config build install wrapup
error: plgwronghook-archive function not defined, cannot get archive
""")

    t.nruns('./scbi plgwronghook/wrong:#v7')

    t.clean_diff("""\
2023/07/27 11:17:42 : Building plgwronghook [wrong] (v7)
2023/07/27 11:17:42 : native x86_64-linux-gnu
2023/07/27 11:17:42 : steps: setup config build install wrapup
error: plgwronghook-wrong-archive function returned 4 values, 5 or 6 expected
""")

    t.runs('./scbi plgwronghook:1.2')

    t.clean_diff("""\
2023/07/27 11:18:07 : Building plgwronghook [default] (1.2)
2023/07/27 11:18:07 : native x86_64-linux-gnu
2023/07/27 11:18:07 : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building plgwronghook [default] (1.2)
""")

    t.nruns('./scbi plgwronghook/wrong:1.2')

    t.clean_diff("""\
2023/07/27 11:18:07 : Building plgwronghook [wrong] (1.2)
2023/07/27 11:18:07 : native x86_64-linux-gnu
2023/07/27 11:18:07 : steps: setup config build install wrapup
error: plgwronghook-wrong-vcs function returned 3 values, 4 or 5 expected
""")
