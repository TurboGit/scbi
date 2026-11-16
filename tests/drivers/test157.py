def test(t):
    t.set('AINST', '$PWD/.root/builds/ahere')

    t.runs('./scbi metaagg-inst/noinst')

    t.nok('-d $AINST')
    t.nok('-f $AINST/include/lib1.h')
    t.nok('-f $AINST/include/lib2.h')
    t.nok('-f $AINST/lib/liblib1.so')
    t.nok('-f $AINST/lib/liblib2.so')

    t.runs('./scbi metaagg-inst')

    t.ok('-d $AINST')
    t.ok('-f $AINST/include/lib1.h')
    t.ok('-f $AINST/include/lib2.h')
    t.ok('-f $AINST/lib/liblib1.so')
    t.ok('-f $AINST/lib/liblib2.so')
