def test(t):
    # check for enable with then/else part

    # === not activated

    t.runs('./scbi -f test60')

    t.runs("grep -h '@@@' .root/builds/test60/build/logs/config.log")

    t.clean_diff("""\
@@@OPT1=
@@@OPT2=
@@@OPT3=native
@@@OPT4 : NOT ENABLED
@@@OPT5 : UNKNOWN
""")

    # === activated

    t.runs('./scbi -f --enable-safe-arch test60')

    t.runs("grep -h '@@@' .root/builds/test60/build/logs/config.log")

    t.clean_diff("""\
@@@OPT1=yes
@@@OPT2=amd
@@@OPT3=i686
@@@OPT4 : ENABLED
@@@OPT5 : UNKNOWN
""")
