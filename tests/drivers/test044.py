def test(t):
    # check skip and command line

    # echo ========== lib1 skip
    t.nruns('./scbi --plan=skip --deps mainmult')

    t.sh("sed -i '/#include/d;/^make:/d;/~~~~~/d;/<builtin>/d;/\\^$/d' $TEST_OUTPUT")

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Module lib1 marked to be skipped

xxxx/xx/xx xx:xx:xx : Building lib2 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ mainmult
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [default] (master)

xxxx/xx/xx xx:xx:xx : Building mainmult [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
cc    -c -o main.o main.c
main.c:2:10: fatal error: lib1.h: No such file or directory
compilation terminated.
xxxx/xx/xx xx:xx:xx : mainmult (FAILED) build failed with error 2
xxxx/xx/xx xx:xx:xx : mainmult (FAILED) to reproduce:
xxxx/xx/xx xx:xx:xx : mainmult (FAILED) <reproduce> <pwd>/.root/builds/mainmult/x86_64-linux-gnu-default/logs/build.cmd
xxxx/xx/xx xx:xx:xx : mainmult (FAILED) use <debug> option for debug
""")

    # echo ========== lib1 forced
    t.runs('./scbi --plan=skip --deps lib1:force')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : apply patch lib1-0-fix.patch
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    t.sh('rm -fr .root/builds/install .root/builds/.logs')

    # echo ========== lib1 forced on mainmult
    t.runs('./scbi --plan=skip --deps lib1:force mainmult')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)

xxxx/xx/xx xx:xx:xx : Building lib2 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ mainmult
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [default] (master)

xxxx/xx/xx xx:xx:xx : Building mainmult [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building mainmult [default] (master)
""")
