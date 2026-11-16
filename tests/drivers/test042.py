def test(t):
    # check call-variant-hooks

    # ============= 0
    t.runs('./scbi varhook')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building varhook [default] (n/a)
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
xxxx/xx/xx xx:xx:xx : End Building varhook [default] (n/a)
""")

    # ============= 1
    t.runs('./scbi varhook/mpi')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building varhook [mpi] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [mpi] starting
xxxx/xx/xx xx:xx:xx : config [mpi] completed
xxxx/xx/xx xx:xx:xx : build [mpi] starting
xxxx/xx/xx xx:xx:xx : build [mpi] completed
xxxx/xx/xx xx:xx:xx : install [mpi] starting
xxxx/xx/xx xx:xx:xx : install [mpi] completed
xxxx/xx/xx xx:xx:xx : End Building varhook [mpi] (n/a)
""")

    # ============= 2
    t.runs('./scbi varhook/mpi.openmp:dev')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building varhook [mpi openmp] (dev)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config [mpi openmp] starting
xxxx/xx/xx xx:xx:xx : config [mpi openmp] completed
xxxx/xx/xx xx:xx:xx : build [mpi openmp] starting
xxxx/xx/xx xx:xx:xx : build [mpi openmp] completed
xxxx/xx/xx xx:xx:xx : install [mpi openmp] starting
xxxx/xx/xx xx:xx:xx : install [mpi openmp] completed
xxxx/xx/xx xx:xx:xx : End Building varhook [mpi openmp] (dev)
""")

    t.runs('grep @@@ .root/builds/.logs/*varhook*config.log')

    t.clean_diff("""\
.root/builds/.logs/x86_64-linux-gnu-varhook-mpi-config.log:@@@ MPI
.root/builds/.logs/x86_64-linux-gnu-varhook-mpi.openmp-config.log:@@@ MPI
.root/builds/.logs/x86_64-linux-gnu-varhook-mpi.openmp-config.log:@@@ OpenMP
""")
