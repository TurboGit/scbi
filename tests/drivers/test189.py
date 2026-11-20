def test(t):
    # plug-in variables (vars) expanded in the context of the hook
    # (is-enabled), available in the command, value and env hooks

    # === not activated

    t.runs('./scbi -f pgvars')

    t.runs("cat .root/builds/pgvars/build/logs/config.log")

    t.clean_diff("""\
OPT1=
OPT2=
OPT3=OFF
OPT4=
OPT5=OFF
OPT6=OFF
CONF=-DBUILD_DOC=OFF -DDEBUG=OFF -DNEW_DEB=OFF -DCO_OPT1=OFF -DCO_OPT2=OFF
ENV=OFF
""")

    # === activated

    t.runs('./scbi -f --enable-doc --enable-debug pgvars')

    t.runs("cat .root/builds/pgvars/build/logs/config.log")

    t.clean_diff("""\
OPT1=yes
OPT2=yes
OPT3=ON
OPT4=yes
OPT5=ON
OPT6=ON
CONF=-DDEBUG=ON -DNEW_DEB=ON -DCO_OPT1=ON -DCO_OPT2=ON
ENV=ON
""")
