def test(t):
    # Add a dummy OS dependency in .pkgs-deb for testing purpose
    t.sh('echo os@-mylualib liblua5.2-dev >> scripts.d/.pkgs-deb')

    t.set('SCBI_OS_NAME', 'deb')
    t.set('SCBI_OS_VERSION', '9.3')
    t.set('SCBI_OS_MAJOR_VERSION', '9')

    t.runs('./scbi show --plan=ondeps --build-plan ondeps')

    t.trim_output()

    t.diff("""\
There is 4 module(s) in the plan
forv9:skip
me:v2
notfound:skip
thisisit:#12
""")

    t.set('SCBI_OS_VERSION', '10.1')
    t.set('SCBI_OS_MAJOR_VERSION', '10')

    t.runs('./scbi show --plan=ondeps --build-plan ondeps')

    t.trim_output()

    t.diff("""\
There is 6 module(s) in the plan
liblua5.2-dev:skip
me:v2
notfound:skip
onlyfor10one:skip
os@-mylualib:skip
thisisit:#12
""")

    t.runs('./scbi --plan=ondeps --deps ondeps')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

xxxx/xx/xx xx:xx:xx : Dependency liblua5.2-dev marked to be skipped

xxxx/xx/xx xx:xx:xx : Dependency os@-mylualib marked to be skipped

xxxx/xx/xx xx:xx:xx : Building ondeps [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building ondeps [default] (master)
""")

    t.unset('SCBI_OS_NAME')
    t.unset('SCBI_OS_VERSION')
    t.unset('SCBI_OS_MAJOR_VERSION')

    # Remove last line added for testing purpose above
    t.sh("sed -i '$ d' scripts.d/.pkgs-deb")
