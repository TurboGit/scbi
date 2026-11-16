def test(t):
    # On plan-dev we have:
    # lib1:v1
    # lib2/variant1:dev

    t.runs('./scbi --plan=dev show --module-ref:full lib1/@:@')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/default:v1
""")

    t.runs('./scbi --plan=dev show --module-ref:full lib1:@')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/default:v1
""")

    t.runs('./scbi --plan=dev show --module-ref:full lib2')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/variant1:dev
""")

    t.runs('./scbi --plan=dev show --module-ref:full lib2/@:@')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/variant1:dev
""")

    t.runs('./scbi --plan=dev show --module-ref:full lib2/@:v88')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/variant1:v88
""")

    t.runs('./scbi --plan=dev show --module-ref:full lib2/me:@')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/me:dev
""")

    t.runs('./scbi --plan=dev show --module-ref:full notset/@:@')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/default
""")
