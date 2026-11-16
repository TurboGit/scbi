def test(t):
    #  build-<target> hooks run by --build-target=<target>

    t.set('TVDIR', '.root/builds/btarget/x86_64-linux-gnu-default')

    t.runs('./scbi -s -c -b btarget')

    t.runs('cat $TVDIR/logs/build.log')

    t.clean_diff("""\
build all
""")

    t.runs('./scbi -f -b --build-target=runtime btarget')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building btarget [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: build
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : build-runtime starting
xxxx/xx/xx xx:xx:xx : build-runtime completed
xxxx/xx/xx xx:xx:xx : End Building btarget [default] (master)
""")

    t.runs('cat $TVDIR/logs/build-runtime.log')

    t.clean_diff("""\
build runtime
""")

    #  no build-<target> hook

    t.nruns('./scbi -f -b --build-target=docs btarget')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building btarget [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: build
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : btarget (FAILED) build failed: no build-docs hook
""")
