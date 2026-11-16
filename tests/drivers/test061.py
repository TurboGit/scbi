def test(t):
    # Check that a change in the SCBI_*_BUILD_TYPE do force a rebuild of modules.

    t.set('LOGC61', '.root/builds/btype/build/logs/config.log')

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
2021/12/09 18:48:32 : config starting
2021/12/09 18:48:32 : config completed
2021/12/09 18:48:32 : build starting
2021/12/09 18:48:32 : build completed
2021/12/09 18:48:32 : install starting
2021/12/09 18:48:32 : install completed
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.grep(*t.words('Release $LOGC61'))

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
2021/12/09 18:48:32 : no build needed: versions matching
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    # Let's change global build-type

    t.set('SCBI_CMAKE_BUILD_TYPE', 'Debug')

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
2021/12/09 18:48:32 : config starting
2021/12/09 18:48:32 : config completed
2021/12/09 18:48:32 : build starting
2021/12/09 18:48:32 : build completed
2021/12/09 18:48:32 : install starting
2021/12/09 18:48:32 : install completed
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.grep(*t.words('Debug $LOGC61'))

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
2021/12/09 18:48:32 : no build needed: versions matching
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.set('SCBI_toto_BUILD_TYPE', 'Debug')

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
2021/12/09 18:48:32 : no build needed: versions matching
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.unset('SCBI_CMAKE_BUILD_TYPE')

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
2021/12/09 18:48:32 : config starting
2021/12/09 18:48:32 : config completed
2021/12/09 18:48:32 : build starting
2021/12/09 18:48:32 : build completed
2021/12/09 18:48:32 : install starting
2021/12/09 18:48:32 : install completed
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.grep(*t.words('Release $LOGC61'))

    t.unset('SCBI_toto_BUILD_TYPE')

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
2021/12/09 18:48:32 : no build needed: versions matching
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.set('SCBI_btype_BUILD_TYPE', 'WhatEver')

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
2021/12/09 18:48:32 : config starting
2021/12/09 18:48:32 : config completed
2021/12/09 18:48:32 : build starting
2021/12/09 18:48:32 : build completed
2021/12/09 18:48:32 : install starting
2021/12/09 18:48:32 : install completed
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.grep(*t.words('WhatEver $LOGC61'))

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
2021/12/09 18:48:32 : no build needed: versions matching
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.unset('SCBI_btype_BUILD_TYPE')

    t.runs('./scbi btype')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building btype [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
2021/12/09 18:48:32 : config starting
2021/12/09 18:48:32 : config completed
2021/12/09 18:48:32 : build starting
2021/12/09 18:48:32 : build completed
2021/12/09 18:48:32 : install starting
2021/12/09 18:48:32 : install completed
2021/12/09 18:48:32 : End Building btype [default] (n/a)
""")

    t.grep(*t.words('Release $LOGC61'))
