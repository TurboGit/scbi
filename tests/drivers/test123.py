def test(t):
    t.set('PDIR', '.root/builds/parent/build/logs')
    t.set('CDIR', '.root/builds/child/build/logs')

    t.runs('./scbi --plan=parchld parent')

    t.grep(*t.words('"OPTIONS: p:1.0" $PDIR/config.log'))
    t.ngrep(*t.words('"OPTIONS: p:1.5" $PDIR/config.log'))

    t.runs('./scbi --plan=parchld child')

    t.ngrep(*t.words('"OPTIONS: p:1.0" $CDIR/config.log'))
    t.grep(*t.words('"OPTIONS: p:1.5" $CDIR/config.log'))
