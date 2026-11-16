def test(t):
    t.set('LDIRD', '.root/builds/dltar2/build/logs')
    t.set('LDIRL', '.root/builds/libppv/build/logs')

    t.runs('./scbi --plan=pv dltar2')

    t.grep(*t.words('"I_VERSION 1" $LDIRD/install.log'))
    t.ngrep(*t.words('"E_VERSION \\"1\\"" $LDIRD/env.cmd'))

    t.runs('./scbi --plan=pv --deps libppv')

    t.grep(*t.words('"E_VERSION \\"2\\"" $LDIRL/env.cmd'))
