def test(t):
    #  Check that changing an inherited plugin do force the recompilation

    #  First build

    t.runs('./scbi child')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building child [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building child [default] (n/a)
""")

    #  Should not build again

    t.runs('./scbi child')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building child [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building child [default] (n/a)
""")

    #  Change parent, should rebuild

    t.sh("sed -i 's/OPTIONS/OOOPTIONS/g' scripts.d/parent.yaml")

    t.runs('./scbi child')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building child [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building child [default] (n/a)
""")

    #  Should not build again

    t.runs('./scbi child')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building child [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building child [default] (n/a)
""")

    #  Change grandparent, should rebuild

    t.sh("sed -i 's/REPLACEME/REPLACED/g' scripts.d/grandparent.yaml")

    t.runs('./scbi child')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building child [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building child [default] (n/a)
""")

    #  Should not build again

    t.runs('./scbi child')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building child [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building child [default] (n/a)
""")

    #  Back to initial version, should rebuild

    t.sh("""\
sed -i 's/REPLACED/REPLACEME/g' scripts.d/grandparent.yaml
sed -i 's/OOOPTIONS/OPTIONS/g' scripts.d/parent.yaml
""")

    t.runs('./scbi child')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building child [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building child [default] (n/a)
""")
