def test(t):
    # Add a dummy OS dependency in .pkgs-deb for testing purpose
    t.sh('echo os@-mynotfound libmynotfound > scripts.d/.pkgs-deb-prj')

    t.nruns('./scbi --deps ondeps/2')

    t.clean_diff("""\
error: missing dependencies for building ondeps/2
error: libmynotfound not found
""")

    t.sh('rm -f scripts.d/.pkgs-deb-prj')
