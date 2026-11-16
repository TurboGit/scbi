def test(t):
    #  The run option of an ini section runs the command in the environment of
    #  the modules (as scbi shell --run=cmd)

    t.set('SCBI_INI_FILE', '$ROOTDIR/.scbiini')

    t.sh("""\
cat <<EOF > $SCBI_INI_FILE
[rundt]
   modules = test2
   run = echo ran with --multi --fr
EOF
""")

    t.runs('./scbi --ini=rundt')

    t.clean_diff("""\
ran with --multi --fr
""")

    t.unset('SCBI_INI_FILE')
