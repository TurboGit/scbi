def test(t):
    # check meta-module env

    t.runs('./scbi metaenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building metaenv [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building metaenv [default] (n/a)
""")

    t.set('LDIR', '.root/builds/metaenv/build/logs')

    t.grep(*t.words('"NAME1 m1"       $LDIR/config.log'))
    t.grep(*t.words('"NAME2 m2"       $LDIR/config.log'))
    t.grep(*t.words('"NAME3 m3"       $LDIR/config.log'))
    t.grep(*t.words('"LIST  m3:m2:m1" $LDIR/config.log'))
