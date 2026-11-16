def test(t):
    # ====== default build

    t.runs('./scbi --tests checkenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building checkenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
toolbin version = 'Release'
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building checkenv [default] (master)
""")

    # ====== force DebugA

    t.set('SCBI_checkenv_BUILD_TYPE', 'DebugA')
    t.runs('./scbi --force --tests checkenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building checkenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
toolbin version = 'DebugA'
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building checkenv [default] (master)
""")

    t.unset('SCBI_checkenv_BUILD_TYPE')

    # ====== force DebugB

    t.set('SCBI_CMAKE_BUILD_TYPE', 'DebugB')
    t.runs('./scbi --force --tests checkenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building checkenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
toolbin version = 'DebugB'
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building checkenv [default] (master)
""")

    t.unset('SCBI_CMAKE_BUILD_TYPE')

    # ====== force DebugC (check precedence)

    t.set('SCBI_checkenv_BUILD_TYPE', 'DebugC')
    t.set('SCBI_CMAKE_BUILD_TYPE', 'DebugB')

    t.runs('./scbi --force --tests checkenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building checkenv [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
toolbin version = 'DebugC'
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building checkenv [default] (master)
""")

    t.unset('SCBI_checkenv_BUILD_TYPE')
    t.unset('SCBI_CMAKE_BUILD_TYPE')
