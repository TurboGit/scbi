def test(t):
    # One report log per module and day (<target>-<module>-report.log):
    # all the messages of the driver for the module, without colors,
    # never truncated.

    t.set('LOGS', '.root/builds/.logs')
    t.set('REPORT', '$LOGS/x86_64-linux-gnu-logmsg-report.log')

    t.runs('./scbi --color:dark logmsg')
    t.runs('./scbi --color:dark --force logmsg')

    # =================== both runs complete in the report, no colors
    t.sh('grep -o "Building logmsg.*\\|trigger: .*\\|wrapup starting\\|End Building.*" $REPORT > $TEST_OUTPUT')
    t.diff("""\
Building logmsg [default] (n/a)
trigger: not yet built
wrapup starting
End Building logmsg [default] (n/a)
Building logmsg [default] (n/a)
trigger: forced
wrapup starting
End Building logmsg [default] (n/a)
""")
    t.sh("grep -c $'\\e' $REPORT > $TEST_OUTPUT")
    t.diff("0\n")
    t.sh('ls $LOGS | grep logmsg | grep report > $TEST_OUTPUT')
    t.diff("x86_64-linux-gnu-logmsg-report.log\n")

    # =================== a meta-module: its triggers in its own report
    t.runs('./scbi --deps metaagg3/agg')
    t.sh('grep -o "Metamodule .*\\|trigger: .*" $LOGS/x86_64-linux-gnu-metaagg3-report.log > $TEST_OUTPUT')
    t.diff("""\
Metamodule metaagg3 [agg] setup
Metamodule metaagg3 [agg] wrapup
trigger: not yet built
""")
    t.sh('grep -c "Metamodule" $LOGS/x86_64-linux-gnu-mainlib-report.log > $TEST_OUTPUT')
    t.diff("0\n")
