def test(t):
    # Check if OS library update triggers the build

    #  Set version for rsync (see osdeps)

    #  installed packages of the fake OS "test" of the testsuite
    t.set('SCBI_TEST_V', '1')
    t.set('SCBI_TEST_PKGS', '"rsync=${SCBI_TEST_V}"')

    t.set('SCBI_OS_NAME', 'test')

    t.runs('./scbi osdeps')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building osdeps [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
2021/12/09 18:48:32 : config starting
2021/12/09 18:48:32 : config completed
2021/12/09 18:48:32 : build starting
2021/12/09 18:48:32 : build completed
2021/12/09 18:48:32 : End Building osdeps [default] (n/a)
""")

    t.runs('./scbi osdeps')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building osdeps [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
2021/12/09 18:48:32 : no build needed: versions matching
2021/12/09 18:48:32 : End Building osdeps [default] (n/a)
""")

    #  Force new version for rsync (see osdeps)

    t.set('SCBI_TEST_V', '2')
    t.set('SCBI_TEST_PKGS', '"rsync=${SCBI_TEST_V}"')

    t.runs('./scbi osdeps')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building osdeps [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
2021/12/09 18:48:32 : config starting
2021/12/09 18:48:32 : config completed
2021/12/09 18:48:32 : build starting
2021/12/09 18:48:32 : build completed
2021/12/09 18:48:32 : End Building osdeps [default] (n/a)
""")

    t.runs('./scbi osdeps')

    t.clean_diff("""\
2021/12/09 18:48:32 : Building osdeps [default] (n/a)
2021/12/09 18:48:32 : native x86_64-linux-gnu
2021/12/09 18:48:32 : steps: setup config build install wrapup
2021/12/09 18:48:32 : no sources (vcs or tar)
2021/12/09 18:48:32 : no build needed: versions matching
2021/12/09 18:48:32 : End Building osdeps [default] (n/a)
""")

    t.unset('SCBI_OS_NAME')
    t.unset('SCBI_TEST_PKGS')
    t.unset('SCBI_OS_VERSION')
    t.unset('SCBI_OS_MAJOR_VERSION')
