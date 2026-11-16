def test(t):
    # check for common / default / variant (config & build hooks)

    t.set('LDIR', '.root/builds/s-par-common/build/logs')

    t.runs('./scbi s-par-common')

    t.grep(*t.words('"CONF-DEF opt-common opt-default opt-std" $LDIR/default-config.log'))

    t.grep(*t.words('"BUILD-STD" $LDIR/build.log'))

    t.runs('./scbi s-par-common/var')

    t.grep(*t.words('"CONF-VAR opt-common opt-var" $LDIR/var-config.log'))

    t.grep(*t.words('"BUILD-VAR" $LDIR/var-build.log'))

    t.runs('./scbi s-par-common/wxt')

    t.grep(*t.words('"CONF-STD opt-common opt-std" $LDIR/config.log'))

    t.grep(*t.words('"BUILD-STD" $LDIR/build.log'))
