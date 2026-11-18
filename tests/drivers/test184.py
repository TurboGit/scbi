def test(t):
    # The build progress [n/N] shows the module being built: a module
    # after its dependencies, its rank in the build order.
    t.set('SCBI_TEST_PROGRESS', 'yes')

    t.runs('./scbi --deps mainlib')
    t.sh('grep -o "^progress .*\\|: Building [a-z0-9]*" $TEST_OUTPUT > out; mv out $TEST_OUTPUT')
    t.diff("""\
progress [1/2] lib1
: Building lib1
progress [2/2] mainlib
: Building mainlib
""")

    # =================== a meta-module: before its modules
    t.runs('./scbi --deps --force metaagg3/agg')
    t.sh('grep -o "^progress .*\\|: Building [a-z0-9]*\\|Metamodule [a-z0-9]* \\[[a-z]*\\] setup"'
         ' $TEST_OUTPUT > out; mv out $TEST_OUTPUT')
    t.diff("""\
progress [1/3] metaagg3/agg
Metamodule metaagg3 [agg] setup
progress [2/3] lib1
: Building lib1
progress [3/3] mainlib
: Building mainlib
""")
    t.unset('SCBI_TEST_PROGRESS')
