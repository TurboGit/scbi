def test(t):
    t.sh("""\
function check-res()
{
    if [[ $1 == 0 ]]; then
        echo FOUND
    else
        echo NOTFOUD
    fi
}
""")

    t.nruns('./scbi store ONE')

    t.runs('./scbi store ONE A')

    t.runs('./scbi store ONE')

    t.sh('echo >> $TEST_OUTPUT')

    t.diff("""\
A
""")

    t.runs('./scbi store SECRET "#this-is-a-long:key:with:some:nonstd%*$chars@"')
    t.runs('./scbi store SECRET')

    t.sh('echo >> $TEST_OUTPUT')

    t.diff(t.text("""\
#this-is-a-long:key:with:some:nonstd%*$chars@
"""))

    t.runs('./scbi store --list-keys')

    t.diff("""\
SECRET
ONE
""")

    t.runs('./scbi store --list ONE')

    t.diff("""\
ONE
""")

    t.runs('./scbi store --list:full ONE')

    t.diff("""\
ONE A
""")

    t.runs('./scbi store --delete SECRET')

    t.runs('./scbi store --list-keys')

    t.diff("""\
ONE
""")

    t.nruns('./scbi store SECRET')

    t.diff('')
