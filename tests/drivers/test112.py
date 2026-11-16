def test(t):
    #  Test inherit of a meta-module: all the hooks (a meta-module too), or
    #  only some (--hooks=setup,wrapup: a module, the modules hook is not
    #  inherited)

    t.runs('./scbi i-supermod')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule i-supermod [default] setup
xxxx/xx/xx xx:xx:xx : setup starting
xxxx/xx/xx xx:xx:xx : setup completed
xxxx/xx/xx xx:xx:xx : End metamodule i-supermod [default] setup

xxxx/xx/xx xx:xx:xx : Metamodule i-supermod [default] wrapup
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : End metamodule i-supermod [default] wrapup
""")

    t.runs('./scbi show --depends i-supermod')

    t.diff("""\
i-supermod
lib1
lib2
""")

    t.runs('./scbi iset-supermod')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building iset-supermod [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : setup starting
xxxx/xx/xx xx:xx:xx : setup completed
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building iset-supermod [default] (n/a)
""")

    t.runs('cat .root/builds/iset-supermod/build/install/supermod')

    t.diff("""\
do setup
do wrapup
""")

    t.runs('./scbi show --depends iset-supermod')

    t.diff("""\
iset-supermod
""")
