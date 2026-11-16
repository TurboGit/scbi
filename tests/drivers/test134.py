def test(t):
    #  Check precedence ENV < INI < COMMAND_LINE

    t.set('SCBI_INI_FILE', '$ROOTDIR/.scbiini')

    t.sh("""\
cat <<EOF > $SCBI_INI_FILE
[std]
        plan = v2

[common]
        env = withplan
        modules = lib1
        no-patch = yes

[twoofthem]
        modules = lib1 lib2
EOF
""")

    # Using plan as defined in environment
    t.runs('./scbi --ini')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v1)
""")

    # Using plan as defined in ini file
    t.runs('./scbi --ini=std')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v2)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v2)
""")

    # Using plan as defined on command line
    t.runs('./scbi --ini=std --plan=skip')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Module lib1 marked to be skipped
""")

    # Using plan as defined in ini file
    t.runs('./scbi --ini=twoofthem')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v1)

xxxx/xx/xx xx:xx:xx : Building lib2 [variant1] (v2.0)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : variant1-config starting
xxxx/xx/xx xx:xx:xx : variant1-config completed
xxxx/xx/xx xx:xx:xx : build [variant1] starting
xxxx/xx/xx xx:xx:xx : build [variant1] completed
xxxx/xx/xx xx:xx:xx : install [variant1] starting
xxxx/xx/xx xx:xx:xx : install [variant1] completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [variant1] (v2.0)
""")

    t.sh("""\
rm -f $SCBI_INI_FILE
unset SCBI_INI_FILE
""")
