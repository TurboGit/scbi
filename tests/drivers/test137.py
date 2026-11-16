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

    # === activated generic

    t.set('SCBI_safe_arch_FEATURE', 'true')

    t.runs('./scbi -f test60')

    t.runs("grep -h '@@@' .root/builds/test60/build/logs/config.log")

    t.clean_diff("""\
@@@OPT1=yes
@@@OPT2=amd
@@@OPT3=i686
@@@OPT4 : ENABLED
@@@OPT5 : UNKNOWN
""")

    # === activated plug-in

    t.set('SCBI_test60_safe_arch_FEATURE', 'true')
    t.unset('SCBI_safe_arch_FEATURE')

    t.runs('./scbi -f test60')

    t.runs("grep -h '@@@' .root/builds/test60/build/logs/config.log")

    t.clean_diff("""\
@@@OPT1=yes
@@@OPT2=amd
@@@OPT3=i686
@@@OPT4 : ENABLED
@@@OPT5 : UNKNOWN
""")

    # === deactivated plug-in

    t.unset('SCBI_test60_safe_arch_FEATURE')

    t.runs('./scbi -f test60')

    t.runs("grep -h '@@@' .root/builds/test60/build/logs/config.log")

    t.clean_diff("""\
@@@OPT1=
@@@OPT2=
@@@OPT3=native
@@@OPT4 : NOT ENABLED
@@@OPT5 : UNKNOWN
""")

    # === deactivated plug-in

    t.set('SCBI_test60_safe_arch_FEATURE', 'false')

    t.runs('./scbi -f test60')

    t.runs("grep -h '@@@' .root/builds/test60/build/logs/config.log")

    t.clean_diff("""\
@@@OPT1=
@@@OPT2=
@@@OPT3=native
@@@OPT4 : NOT ENABLED
@@@OPT5 : UNKNOWN
""")

    # === deactivated plug-in even if activated commande line

    t.set('SCBI_test60_safe_arch_FEATURE', 'false')
    t.set('SCBI_safe_arch_FEATURE', 'false')

    t.runs('./scbi -f --enable-safe-arch test60')

    t.runs("grep -h '@@@' .root/builds/test60/build/logs/config.log")

    t.clean_diff("""\
@@@OPT1=yes
@@@OPT2=amd
@@@OPT3=i686
@@@OPT4 : ENABLED
@@@OPT5 : UNKNOWN
""")
