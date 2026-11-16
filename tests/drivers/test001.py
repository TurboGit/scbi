def test(t):
    # simple check

    t.set('REP', '$PWD/.root/builds/test1')

    t.runs('./scbi -s -c test1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building test1 [default] (master)
""")

    #  Check that the directory sync is properly done with hard links

    t.sh("""\
I1=( $(ls -i $REP/src/Makefile) )
I2=( $(ls -i $REP/x86_64-linux-gnu-default/src/Makefile) )
""")

    t.is_('${I1[0]}', '==', '${I2[0]}')
