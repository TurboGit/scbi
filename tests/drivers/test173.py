def test(t):
    t.runs('./scbi --env=dump m-lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building m-lib1 [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : final step starting
xxxx/xx/xx xx:xx:xx : final step completed
xxxx/xx/xx xx:xx:xx : End Building m-lib1 [default] (n/a)
""")

    t.set('ENVDUMP', '.root/builds/m-lib1/env.dump')

    t.grep(*t.words('"A:ADD C_INCLUDE_PATH = a" $ENVDUMP'))
    t.grep(*t.words('"A:PREPEND LD_LIBRARY_PATH = b" $ENVDUMP'))
    t.grep(*t.words('"A:APPEND LIBRARY_PATH = c" $ENVDUMP'))
    t.grep(*t.words('"A:SET C_INCLUDE_PATH = be:a" $ENVDUMP'))
    t.grep(*t.words('"A:SET LIBRARY_PATH = be:.:b" $ENVDUMP'))
    t.grep(*t.words('"A:SET LD_LIBRARY_PATH = be:.:c" $ENVDUMP'))
