def test(t):
    # fake build dependencies (variants) not present

    t.sh("""\
for v in one two three four; do
    mkdir -p .root/builds/$v
done
""")

    # check that we properly pass variants
    # ========== build/install var
    t.runs('./scbi var')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building var [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building var [default] (n/a)
""")

    # ========== build/install var/one
    t.runs('./scbi var/one')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building var [one] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [one] starting
xxxx/xx/xx xx:xx:xx : config [one] completed
xxxx/xx/xx xx:xx:xx : build [one] starting
xxxx/xx/xx xx:xx:xx : build [one] completed
xxxx/xx/xx xx:xx:xx : install [one] starting
xxxx/xx/xx xx:xx:xx : install [one] completed
xxxx/xx/xx xx:xx:xx : End Building var [one] (n/a)
""")

    # ========== build/install var/two
    t.runs('./scbi var/two')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building var [two] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [two] starting
xxxx/xx/xx xx:xx:xx : config [two] completed
xxxx/xx/xx xx:xx:xx : build [two] starting
xxxx/xx/xx xx:xx:xx : build [two] completed
xxxx/xx/xx xx:xx:xx : install [two] starting
xxxx/xx/xx xx:xx:xx : install [two] completed
xxxx/xx/xx xx:xx:xx : End Building var [two] (n/a)
""")

    # ========== build/install var/one.two
    t.runs('./scbi var/one.two')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building var [one two] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [one two] starting
xxxx/xx/xx xx:xx:xx : config [one two] completed
xxxx/xx/xx xx:xx:xx : build [one two] starting
xxxx/xx/xx xx:xx:xx : build [one two] completed
xxxx/xx/xx xx:xx:xx : install [one two] starting
xxxx/xx/xx xx:xx:xx : install [one two] completed
xxxx/xx/xx xx:xx:xx : End Building var [one two] (n/a)
""")

    # ========== build/install var/two.one
    t.runs('./scbi var/two.one')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building var [two one] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [two one] starting
xxxx/xx/xx xx:xx:xx : config [two one] completed
xxxx/xx/xx xx:xx:xx : build [two one] starting
xxxx/xx/xx xx:xx:xx : build [two one] completed
xxxx/xx/xx xx:xx:xx : install [two one] starting
xxxx/xx/xx xx:xx:xx : install [two one] completed
xxxx/xx/xx xx:xx:xx : End Building var [two one] (n/a)
""")

    # ========== build/install var/one.two.three.four
    t.runs('./scbi var/one.two.three.four')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building var [one two three four] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [one two three four] starting
xxxx/xx/xx xx:xx:xx : config [one two three four] completed
xxxx/xx/xx xx:xx:xx : build [one two three four] starting
xxxx/xx/xx xx:xx:xx : build [one two three four] completed
xxxx/xx/xx xx:xx:xx : install [one two three four] starting
xxxx/xx/xx xx:xx:xx : install [one two three four] completed
xxxx/xx/xx xx:xx:xx : End Building var [one two three four] (n/a)
""")

    t.set('LPRE', '.root/builds/.logs/x86_64-linux-gnu')

    t.runs("grep -h '@@@' $(ls -t $LPRE-var-one-*.log)")

    t.clean_diff("""\
@@@ install var: one
@@@ install      one
@@@ build var: one
@@@ build      one
@@@ config var: one
@@@ config      one
""")

    t.runs("grep -h '@@@' $(ls -t $LPRE-var-two-*.log)")

    t.clean_diff("""\
@@@ install var: two
@@@ install      two
@@@ build var: two
@@@ build      two
@@@ config var: two
@@@ config      two
""")

    t.runs("grep -h '@@@' $(ls -t $LPRE-var-one.two-*.log)")

    t.clean_diff("""\
@@@ install var: one.two
@@@ install      one
@@@ install      two
@@@ build var: one.two
@@@ build      one
@@@ build      two
@@@ config var: one.two
@@@ config      one
@@@ config      two
""")

    t.runs("grep -h '@@@' $(ls -t $LPRE-var-two.one-*.log)")

    t.clean_diff("""\
@@@ install var: two.one
@@@ install      two
@@@ install      one
@@@ build var: two.one
@@@ build      two
@@@ build      one
@@@ config var: two.one
@@@ config      two
@@@ config      one
""")

    t.runs("grep -h '@@@' $(ls -t $LPRE-var-one.two.three.four-*.log)")

    t.clean_diff("""\
@@@ install var: one.two.three.four
@@@ install      one
@@@ install      two
@@@ install      three
@@@ install      four
@@@ build var: one.two.three.four
@@@ build      one
@@@ build      two
@@@ build      three
@@@ build      four
@@@ config var: one.two.three.four
@@@ config      one
@@@ config      two
@@@ config      three
@@@ config      four
""")
