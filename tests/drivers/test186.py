def test(t):
    # One report log per module and day (<target>-<module>-report.log):
    # all the messages of the driver for the module, without colors,
    # never truncated; the log command of the command hooks.

    t.set('LOGS', '.root/builds/.logs')
    t.set('REPORT', '$LOGS/x86_64-linux-gnu-logmsg-report.log')

    t.runs('./scbi --color:dark logmsg')
    t.runs('./scbi --color:no --force logmsg')

    # =================== the log command: driver messages, indented
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building logmsg [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx :   working on step 1
xxxx/xx/xx xx:xx:xx :   working on step 2
xxxx/xx/xx xx:xx:xx :     working on step 2.1
xxxx/xx/xx xx:xx:xx :     working on step 2.2
xxxx/xx/xx xx:xx:xx :   50% done
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : End Building logmsg [default] (n/a)
""")

    # =================== in the report log (both runs) and the step logs
    t.sh('grep -c " :     working on step 2.1$" $REPORT > $TEST_OUTPUT')
    t.diff("2\n")
    t.sh('grep -o " :   .*\\|^plain$" .root/builds/logmsg/x86_64-linux-gnu-default/logs/wrapup.log'
         ' > $TEST_OUTPUT')
    t.diff("""\
 :   working on step 1
 :   working on step 2
 :     working on step 2.1
 :     working on step 2.2
 :   50% done
plain
""")
    t.sh('grep -c " :     working on step 2.1$" $LOGS/x86_64-linux-gnu-logmsg-default-wrapup.log > $TEST_OUTPUT')
    t.diff("2\n")

    # =================== --quiet: in the logs, not on the console
    t.runs('./scbi --quiet --force logmsg')
    t.ngrep('working on')
    t.sh('grep -c " :   working on step 1$" $REPORT > $TEST_OUTPUT')
    t.diff("3\n")

    # =================== a bad level: the step fails
    t.sh("sed -i 's/^  echo plain$/  log 0 bad/' scripts.d/logmsg.yaml")
    t.nruns('./scbi --force logmsg')
    t.grep('wrapup failed')
    t.sh('grep -c "log: level must be an integer >= 1" '
         '.root/builds/logmsg/x86_64-linux-gnu-default/logs/wrapup.log > $TEST_OUTPUT')
    t.diff("1\n")
    t.sh("sed -i 's/^  log 0 bad$/  echo plain/' scripts.d/logmsg.yaml")

    # =================== both runs complete in the report, no colors
    t.sh('grep -o "Building logmsg.*\\|trigger: .*\\|wrapup starting\\|wrapup failed.*\\|End Building.*" '
         '$REPORT > $TEST_OUTPUT')
    t.diff("""\
Building logmsg [default] (n/a)
trigger: not yet built
wrapup starting
End Building logmsg [default] (n/a)
Building logmsg [default] (n/a)
trigger: forced
wrapup starting
End Building logmsg [default] (n/a)
Building logmsg [default] (n/a)
trigger: forced
wrapup starting
End Building logmsg [default] (n/a)
Building logmsg [default] (n/a)
trigger: forced
wrapup starting
wrapup failed with error 1
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
