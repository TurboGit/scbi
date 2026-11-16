def test(t):
    # test build plan with a :dev version

    # =================== module ref (v1)
    t.runs('./scbi show --plan=dev --module-ref:version lib1')
    # add eof to osht output
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
v1
""")

    # =================== module ref (v2)
    t.runs('./scbi show --plan=dev --module-ref:version lib1:v2')
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
v2
""")

    # =================== module ref (NONE)
    t.runs('./scbi show --module-ref:version lib1')
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
NONE
""")

    # =================== module ref (default)
    t.runs('./scbi show --plan=dev --module-ref:variant lib1')
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
default
""")

    # =================== module ref (/variant1:dev)
    t.runs('./scbi show --plan=dev --module-ref:full lib2')
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/variant1:dev
""")

    # =================== module ref (/variant1:dev)
    t.runs('./scbi show --plan=dev --module-ref lib2')
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
/variant1:dev
""")

    # =================== module ref (default & variant1)
    t.runs('./scbi show --plan=dev --module-ref:variant lib1 lib2')
    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
default
variant1
""")
