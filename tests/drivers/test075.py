def test(t):
    # check for version in plug-in

    t.set('LDIR', '.root/builds/libpv/build/logs')

    t.runs('./scbi libpv')

    t.grep(*t.words('"VERSION-C NONE" $LDIR/config.log'))
    t.grep(*t.words('"VERSION-B NONE" $LDIR/build.log'))
    t.grep(*t.words('"VERSION-I NONE" $LDIR/install.log'))
    t.grep(*t.words('"VERSION-BE NONE" $LDIR/config.log'))
    t.grep(*t.words('"VERSION-BE NONE" $LDIR/build.log'))
    t.grep(*t.words('"VERSION-BE NONE" $LDIR/install.log'))

    t.runs('./scbi libpv:v1')

    t.grep(*t.words('"VERSION-C v1" $LDIR/config.log'))
    t.grep(*t.words('"VERSION-B v1" $LDIR/build.log'))
    t.grep(*t.words('"VERSION-I v1" $LDIR/install.log'))
    t.grep(*t.words('"VERSION-BE v1" $LDIR/install.log'))
    t.grep(*t.words('"LE 1" $LDIR/build.log'))

    t.runs('./scbi libpv:v1.2')

    t.grep(*t.words('"VERSION-C v1.2" $LDIR/config.log'))
    t.grep(*t.words('"VERSION-B v1.2" $LDIR/build.log'))
    t.grep(*t.words('"VERSION-I v1.2" $LDIR/install.log'))
    t.grep(*t.words('"VERSION-BE v1.2" $LDIR/config.log'))
    t.grep(*t.words('"VERSION-BE v1.2" $LDIR/build.log'))
    t.grep(*t.words('"VERSION-BE v1.2" $LDIR/install.log'))
    t.grep(*t.words('"GT 1" $LDIR/build.log'))
