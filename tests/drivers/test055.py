def test(t):
    # Check cross depends with variants

    # ========== OPT-A
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcross/opta')

    t.diff("""\
error: missing dependencies for building mcross/opta
error: cross-opta not found
""")

    # ========== OPT-B
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcross/optb:v8')

    t.diff("""\
error: missing dependencies for building mcross/optb
error: cross-optb not found
""")

    # ========== OPT-A + OPT-B
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcross/opta.optb')

    t.diff("""\
error: missing dependencies for building mcross/opta.optb
error: cross-opta not found
error: cross-optb not found
""")

    # ========== NO-OPT
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcross')

    t.diff("""\
error: missing dependencies for building mcross
error: cross-general not found
""")

    # ========== OPT-A
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcrossc/opta')

    t.diff("""\
error: missing dependencies for building mcrossc/opta
error: crossc-common not found
error: crossc-opta not found
""")

    # ========== OPT-B
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcrossc/optb:v8')

    t.diff("""\
error: missing dependencies for building mcrossc/optb
error: crossc-common not found
error: crossc-optb not found
""")

    # ========== OPT-A + OPT-B
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcrossc/opta.optb')

    t.diff("""\
error: missing dependencies for building mcrossc/opta.optb
error: crossc-common not found
error: crossc-opta not found
error: crossc-optb not found
""")

    # ========== NO-OPT
    t.nruns('./scbi --deps --target=x86_64-pc-mingw32 mcrossc')

    t.diff("""\
error: missing dependencies for building mcrossc
error: crossc-common not found
error: crossc-general not found
""")
