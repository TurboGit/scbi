def test(t):
    # An ini file loaded once when it is both ./.scbi and $SCBI_INI_FILE
    # (as $HOME/.scbi when run from $HOME): its modules are not doubled.
    # A module given twice is built once.

    t.set('SCBI_INI_FILE', '$PWD/.scbi')

    t.sh("""\
cat <<EOF > .scbi
[two]
   modules = mainlib lib1
EOF
""")

    t.runs('./scbi --dry-run --ini=two')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : build order: lib1 mainlib
lib1
mainlib
""")

    t.unset('SCBI_INI_FILE')
    t.sh("rm -f .scbi")

    t.runs('./scbi --dry-run mainlib lib1 mainlib lib1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : build order: lib1 mainlib
lib1
mainlib
""")
