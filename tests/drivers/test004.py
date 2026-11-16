def test(t):
    # check that different versions are properly built
    #
    # use local environment

    t.set('REP', '$PWD/.root/builds/lib1')

    t.runs('./scbi --no-patch --tests lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.C master
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    t.grep(*t.words('"lib1 git master sha-1 eb90bc4f3553280d80aef0250dc37ad2fd174636" $REP/source-ref'))

    t.runs('./scbi --no-patch --tests --archive lib1:v1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.A br_a
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v1)
""")

    t.grep(*t.words('"lib1 git v1 sha-1 494a8908b2a4b6cca336cf39e8f1fa4fd37b370a" $REP/source-ref'))

    t.runs('./scbi --no-patch --tests --archive lib1:v2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v2)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.D br_b
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v2)
""")

    t.grep(*t.words('"lib1 git v2 sha-1 4f8776f351fb5eabdd62effe85958472477f371a" $REP/source-ref'))

    t.nok('-h $REP/tar')

    t.runs('./scbi --no-patch --tests --archive lib1:#v1.2')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v1.2)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from archive
xxxx/xx/xx xx:xx:xx : extract archive lib1-v1.2-src.tar.bz2
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
lib from tar
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v1.2)
""")

    t.grep(*t.words('"lib1 archive v1.2 sha-1 631429bf5f27d5aec4d7e41394e0d2eaa3a8da2d" $REP/source-ref'))

    t.ok('-h $REP/archive')

    t.runs('./scbi --no-patch --tests lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.C master
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")
