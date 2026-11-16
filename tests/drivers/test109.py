def test(t):
    # check that different versions are properly built
    #
    # use local environment

    t.set('SCBI_INI_FILE', '$ROOTDIR/.scbiini')

    t.sh("""\
cat <<EOF > $SCBI_INI_FILE
[lib1]
   modules = lib1
   tests = only

[stest]
   setup = yes
   config = yes
   modules = stest
   tests = yes
   tests-list = "opt1 opt2"

[common]
   quiet = yes
EOF
""")

    t.nruns('./scbi --ini=lib1')

    t.runs('./scbi lib1')

    t.runs('./scbi --ini=lib1')

    t.diff("""\
main
liba.C patched version
""")

    t.runs('./scbi --ini=stest')

    t.diff("""\
stest: opt1 opt2
""")

    t.sh('rm $SCBI_INI_FILE')
