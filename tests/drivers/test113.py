def test(t):
    t.runs('./scbi --tests libinh1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building libinh1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : apply patch lib1-0-fix.patch
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.C patched version
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building libinh1 [default] (master)
""")

    #sed -i 's/export SCBI_PLUGINS/#export SCBI_PLUGINS/'  #    .root/builds/libinh1/build/logs/env.cmd

    t.runs('./scbi replay .root/builds/libinh1/build/logs/build.cmd')

    t.clean_diff("""\
cc    -c -o lib1.o lib1.c
ar cr liblib1.a lib1.o
gcc -shared -o liblib1.so lib1.o
cc    -c -o main.o main.c
gcc -o main main.o -llib1
""")

    t.runs('./scbi replay .root/builds/libinh1/build/logs/tests.cmd')

    t.clean_diff("""\
main
liba.C patched version
""")
