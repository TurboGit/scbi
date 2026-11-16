def test(t):
    #  Test inherit with --no-variant and --hooks: the hooks run (@@@ lines of
    #  the step logs, sorted by log file name)

    t.set('LOGS', '.root/builds/.logs')

    #  --no-variant: only the hooks without variant are inherited
    t.runs('./scbi inv-test19/alt')

    t.runs("grep -h '^@@@' $LOGS/*inv-test19*")

    t.clean_diff("""\
@@@ BUILD  inv-test19/x86_64-linux-gnu-alt/src
@@@ CONFIG  inv-test19/x86_64-linux-gnu-alt/src
@@@ INSTALL  inv-test19/x86_64-linux-gnu-alt/src
@@@ POST-BUILD  inv-test19/x86_64-linux-gnu-alt/src
@@@ POST-CONFIG  inv-test19/x86_64-linux-gnu-alt/src
@@@ PRE-BUILD  inv-test19/x86_64-linux-gnu-alt/src
@@@ PRE-INSTALL  inv-test19/x86_64-linux-gnu-alt/src
@@@ PRE-SETUP  inv-test19
@@@ PRE-WRAPUP  inv-test19
@@@ WRAPUP  inv-test19
""")

    #  --no-variant --hooks=build,setup: build and setup steps only (with their
    #  pre/post hooks), not out-of-tree (built in build)
    t.runs('./scbi invset-test19/alt')

    t.runs("grep -h '^@@@' $LOGS/*invset-test19*")

    t.clean_diff("""\
@@@ BUILD  invset-test19/x86_64-linux-gnu-alt/build
@@@ POST-BUILD  invset-test19/x86_64-linux-gnu-alt/build
@@@ PRE-BUILD  invset-test19/x86_64-linux-gnu-alt/build
@@@ PRE-SETUP  invset-test19
""")

    #  --hooks=build,setup with the variants
    t.runs('./scbi iset-test19/alt')

    t.runs("grep -h '^@@@' $LOGS/*iset-test19-alt*")

    t.clean_diff("""\
@@@ ALT/PRE-SETUP  iset-test19
@@@ BUILD  iset-test19/x86_64-linux-gnu-alt/build
@@@ POST-BUILD  iset-test19/x86_64-linux-gnu-alt/build
@@@ PRE-BUILD  iset-test19/x86_64-linux-gnu-alt/build
""")
