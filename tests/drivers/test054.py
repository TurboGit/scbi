def test(t):
    # Check handling of parameters with spaces & get-config-options

    t.set('MDIR', '.root/builds/mspace')

    # ========== OPT-A
    t.runs('./scbi mspace/opta')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building mspace [opta] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : opta-config starting
xxxx/xx/xx xx:xx:xx : opta-config completed
xxxx/xx/xx xx:xx:xx : End Building mspace [opta] (n/a)
""")

    t.runs('grep "^[A-F] " $MDIR/x86_64-linux-gnu-opta/logs/opta-config.log')

    t.clean_diff("""\
A one
B two
C -DLIB=-L/usr/lib -lmpi_cxx -lmpi
""")

    # ========== OPT-B
    t.runs('./scbi mspace/optb')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building mspace [optb] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : optb-config starting
xxxx/xx/xx xx:xx:xx : optb-config completed
xxxx/xx/xx xx:xx:xx : End Building mspace [optb] (n/a)
""")

    t.runs('grep "^[A-F] " $MDIR/x86_64-linux-gnu-optb/logs/optb-config.log')

    t.clean_diff("""\
A one
B two
C -DLIB=-lz1 -lz2 -lz3
""")

    # ========== OPT-A + OPT-B
    t.runs('./scbi mspace/opta.optb')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building mspace [opta optb] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : opta-config [opta optb] starting
xxxx/xx/xx xx:xx:xx : opta-config [opta optb] completed
xxxx/xx/xx xx:xx:xx : End Building mspace [opta optb] (n/a)
""")

    t.runs('grep "^[A-F] " $MDIR/x86_64-linux-gnu-opta.optb/logs/opta-config.log')

    t.clean_diff("""\
A one
B two
C -DLIB=-L/usr/lib -lmpi_cxx -lmpi
D -DLIB=-lz1 -lz2 -lz3
""")

    # ========== OPT-B + OPT-A
    t.runs('./scbi mspace/optb.opta')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building mspace [optb opta] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : optb-config [optb opta] starting
xxxx/xx/xx xx:xx:xx : optb-config [optb opta] completed
xxxx/xx/xx xx:xx:xx : End Building mspace [optb opta] (n/a)
""")

    t.runs('grep "^[A-F] " $MDIR/x86_64-linux-gnu-optb.opta/logs/optb-config.log')

    t.clean_diff("""\
A one
B two
C -DLIB=-lz1 -lz2 -lz3
D -DLIB=-L/usr/lib -lmpi_cxx -lmpi
""")
