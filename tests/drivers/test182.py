def test(t):
    # Without --deps the modules of the command line are built after
    # their dependencies (direct or not, through meta-modules too), the
    # given order kept otherwise.

    # =================== direct dependency: lib1 before mainlib
    t.runs('./scbi --dry-run mainlib lib1')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : build order: lib1 mainlib
lib1
mainlib
""")

    # =================== dependency and build dependency
    t.runs('./scbi --dry-run bdepslib1 lib1 lib2')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : build order: lib1 lib2 bdepslib1
lib1
lib2
bdepslib1
""")

    # =================== transitive, through a meta-module:
    # usemetaagg3 -> metaagg3 -> mainlib -> lib1
    t.runs('./scbi --dry-run usemetaagg3 lib1 mainlib')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : build order: lib1 mainlib usemetaagg3
lib1
mainlib
usemetaagg3
""")

    # =================== already in order, independent modules: unchanged
    t.runs('./scbi --dry-run lib1 mainlib')
    t.clean_diff("""\
lib1
mainlib
""")
    t.runs('./scbi --dry-run lib2 lib1')
    t.clean_diff("""\
lib2
lib1
""")

    # =================== with --deps the dependencies are built first anyway
    t.runs('./scbi --dry-run --deps mainlib lib1')
    t.ngrep('build order')

    # =================== a real build in the new order
    t.runs('./scbi mainlib lib1')
    t.grep('build order: lib1 mainlib')
    t.sh('grep -o ": Building [a-z0-9]*" $TEST_OUTPUT | cut -c3- > building; mv building $TEST_OUTPUT')
    t.diff("""\
Building lib1
Building mainlib
""")
