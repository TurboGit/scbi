def test(t):
    # Check for corrupted tar

    t.sh('rm -f .root/.archives/dltar-src.tar.bz2*')

    t.sh("""\
cp .root/.store/dltar-1-src.tar.bz2 .root/.store/dltar-src.tar.bz2
cp .root/.store/dltar-1-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1
""")

    t.runs('./scbi --tests --update dltar:#0')

    t.clean_diff("""\
2022/01/04 19:22:11 : Building dltar [default] (0)
2022/01/04 19:22:11 : native x86_64-linux-gnu
2022/01/04 19:22:11 : steps: setup config build install tests wrapup
2022/01/04 19:22:11 : get sources from archive
xxxx/xx/xx xx:xx:xx : extract archive dltar-src.tar.bz2
xxxx/xx/xx xx:xx:xx : trigger: not yet built
2022/01/04 19:22:11 : install starting
2022/01/04 19:22:11 : install completed
2022/01/04 19:22:11 : tests starting
Script 1
2022/01/04 19:22:11 : tests completed
2022/01/04 19:22:11 : copy install into <sandbox>/install
2022/01/04 19:22:11 : End Building dltar [default] (0)
""")

    #  Corruped archive, check that the error message is clear

    t.sh('rm -f .root/.archives/dltar-src.tar.bz2*')

    t.sh("""\
cp .root/.store/dltar-1-src.tar.bz2 .root/.store/dltar-src.tar.bz2
cp .root/.store/dltar-1-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1
""")

    t.sh('truncate -s 100 .root/.store/dltar-src.tar.bz2')

    t.nruns('./scbi --tests --update dltar:#0')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

xxxx/xx/xx xx:xx:xx : Building dltar [default] (0)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from archive
xxxx/xx/xx xx:xx:xx : extract archive dltar-src.tar.bz2
xxxx/xx/xx xx:xx:xx : dltar (FAILED) archive dltar-src.tar.bz2 is corrupted
xxxx/xx/xx xx:xx:xx : cannot get/find/extract archive sources
""")

    t.grep(*t.words('"tar: Error is not recoverable" .root/builds/.logs/*dltar*report.log'))
