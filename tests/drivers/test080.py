def test(t):
    # check that patches are properly applied if present

    # echo ========== lib1 patched version
    t.nruns('./scbi withpatch')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building withpatch [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-com-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-def-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-0-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) generic module setup failed with error 1
""")

    t.nruns('./scbi withpatch/default')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building withpatch [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-com-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-def-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-0-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) generic module setup failed with error 1
""")

    t.nruns('./scbi withpatch/var')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building withpatch [var] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-com-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-var-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) generic module setup failed with error 1
""")

    t.nruns('./scbi withpatch/default.var')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building withpatch [default var] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-com-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-def-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) patch withpatch-var-fix.patch not found
xxxx/xx/xx xx:xx:xx : withpatch (FAILED) generic module setup failed with error 1
""")
