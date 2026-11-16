def test(t):
    #  Check that prefix is working on .ini

    t.set('SCBI_INI_FILE', '$ROOTDIR/.scbiini')

    t.sh("""\
cat <<EOF > $SCBI_INI_FILE
[std]
        modules = gentool
        prefix = $ROOTDIR/.root/builds/pints
EOF
""")

    # Using plan as defined in environment
    t.runs('./scbi --ini=std')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building gentool [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/pints
xxxx/xx/xx xx:xx:xx : End Building gentool [default] (n/a)
""")

    t.sh("""\
rm -f $SCBI_INI_FILE
rm -fr $ROOTDIR/.root/builds/pints
unset SCBI_INI_FILE
""")
