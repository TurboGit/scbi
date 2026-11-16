def test(t):
    t.sh("""\
cp scripts.d/test2.yaml scripts.d/test99.yaml
sed -i 's/^plugin: test2$/plugin: test99/' scripts.d/test99.yaml
""")

    t.runs('./scbi test99')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test99 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building test99 [default] (master)
""")

    t.runs('./scbi test99')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test99 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building test99 [default] (master)
""")

    t.sh("sed -i 's/make/make -j2/g' scripts.d/test99.yaml")

    t.runs('./scbi test99')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test99 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building test99 [default] (master)
""")

    t.sh('rm scripts.d/test99.yaml')
