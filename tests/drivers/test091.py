def test(t):
    #  Check for --prefix & --build-dir

    t.runs('./scbi --prefix=$PWD/inst lib1')

    t.ok('-d $PWD/inst')
    t.ok('-f $PWD/inst/lib/liblib1.so')
    t.ok('-f $PWD/inst/include/lib1.h')

    t.sh('rm -fr $PWD/inst')

    t.runs('./scbi --build-dir=$PWD/sb lib1')

    t.ok('-d $PWD/sb')
    t.ok('-d $PWD/sb/lib1')
    t.ok('-f $PWD/sb/lib1/source-id')
    t.ok('-d $PWD/sb/install')

    t.sh('rm -fr sb')

    t.runs('./scbi --build-dir=$PWD/sbnew --prefix=$PWD/here lib1')

    t.ok('-d $PWD/sbnew')
    t.ok('-d $PWD/sbnew/lib1')
    t.ok('-f $PWD/sbnew/lib1/source-id')
    t.nok('-d $PWD/sbnew/install')
    t.ok('-d $PWD/here')

    t.sh("""\
rm -fr sbnew
rm -fr here
""")
