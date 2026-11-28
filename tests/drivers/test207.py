def test(t):
    # the time of the steps of the modules: <target>-steps.log in the log
    # directory, summarized for the last run by --stat:full

    t.set('STEPS', '.root/builds/.logs/$TODAY/x86_64-linux-gnu-steps.log')
    t.sh('printf "pre-build: sleep 1\n" >> scripts.d/lib1.yaml')

    t.runs('./scbi -d mainlib')

    t.runs('cut -f3,4,5,9 $STEPS')
    t.clean_diff("""\
lib1	default	setup	0
lib1	default	config	0
lib1	default	build	0
lib1	default	install	0
lib1	default	wrapup	0
mainlib	default	setup	0
mainlib	default	config	0
mainlib	default	build	0
mainlib	default	install	0
mainlib	default	wrapup	0
""")

    # one run id for the run (the modules last more than a second)
    t.runs('cut -f1 $STEPS | sort -u | wc -l')
    t.clean_diff("""\
1
""")

    # an up-to-date module has no step
    t.runs('./scbi -d mainlib')
    t.runs('wc -l < $STEPS')
    t.clean_diff("""\
10
""")

    # a failing step is recorded with its status (1: the hook failed)
    t.sh('printf "build: exit 3\\n" >> scripts.d/lib1.yaml')
    t.nruns('./scbi --force lib1')
    t.runs('tail -1 $STEPS | cut -f3,5,9')
    t.clean_diff("""\
lib1	build	1
""")

    t.runs('./scbi --stat:full')
    t.sh('sed -n "/^steps of the last build/,\\$p" $TEST_OUTPUT'
         ' | sed -e "s/, run .*):/):/" -e "s/[0-9]*:[0-9][0-9]:[0-9][0-9]/H:MM:SS/g"'
         ' -e "s/  *[0-9.-]*$/ N/" -e "s/[0-9-][0-9]*%* of the/N of the/" -e "s/ [0-9-][0-9]*%* of SCBI/ N of SCBI/" > x; mv x $TEST_OUTPUT')
    t.clean_diff("""\
steps of the last build (1 module(s)):

step            wall       cpu  cores used
setup        H:MM:SS   H:MM:SS N
config       H:MM:SS   H:MM:SS N
build        H:MM:SS   H:MM:SS N
total        H:MM:SS   H:MM:SS

steps using many cores (build, tests): H:MM:SS, N of the time
other steps: H:MM:SS, N of the time
CPU used: N of SCBI_JOBS cores during the steps

""")
