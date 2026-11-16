def test(t):
    # check for common / default / variant (config & build hooks)

    t.set('LDIR', '.root/builds/hookskind/build/logs')

    t.runs('./scbi hookskind')

    t.grep(*t.words('"CONF-DEF opt-common opt-default opt-std" $LDIR/default-config.log'))

    t.grep(*t.words('"BUILD-STD" $LDIR/build.log'))

    t.runs('./scbi hookskind/var')

    t.grep(*t.words('"CONF-VAR opt-common opt-var" $LDIR/var-config.log'))

    t.grep(*t.words('"BUILD-VAR" $LDIR/var-build.log'))

    t.runs('./scbi hookskind/wxt')

    t.grep(*t.words('"CONF-STD opt-common opt-std" $LDIR/config.log'))

    t.grep(*t.words('"BUILD-STD" $LDIR/build.log'))
