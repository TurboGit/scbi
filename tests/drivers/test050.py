def test(t):
    # ========= should fail

    t.nruns('./scbi --setup --tests:only checkvcs')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building checkvcs [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup tests
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : error: cannot get sources from /this.is.path/some/dir
xxxx/xx/xx xx:xx:xx : error: see <pwd>/.root/builds/.logs//x86_64-linux-gnu-checkvcs-default-report.log
""")

    #  the vcs records are rewritten by the environment (.env-rewrite)

    # ========= should be ok
    t.runs('./scbi --env=rewrite --setup --tests:only checkvcs')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building checkvcs [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup tests
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : End Building checkvcs [default] (master)
""")
