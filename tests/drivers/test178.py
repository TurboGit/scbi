def test(t):
    #  all-modules (with the status of the modules) and hook-output

    t.runs('./scbi --deps allmods')

    t.runs('cat .root/builds/allmods/x86_64-linux-gnu-default/logs/wrapup.log')

    t.clean_diff("""\
lib1: aggregated
libenv: aggregated
metaagg: depends-kind=default meta aggregate=yes
test2: depends-kind=default
inhnat: depends-kind=default
lib3: depends-kind=build
allmods: depends-kind=default
modules of metaagg: lib1 libenv
test-dir: EDF/x/tests
no hook: []
""")
