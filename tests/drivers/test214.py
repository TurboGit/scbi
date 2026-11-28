def test(t):
    # purge@<module>: only this module purged before its build
    #

    t.runs('./scbi --no-patch --deps dep1')
    t.grep('Building lib1')
    t.grep('Building dep1')

    # the dependency only: lib1 purged and rebuilt, dep1 not purged
    t.runs('./scbi --no-patch --deps purge@lib1 dep1')
    t.grep('Purging lib1')
    t.ngrep('Purging dep1')
    t.grep('Building lib1')

    # the purge@ module reached as a dependency first
    t.runs('./scbi --no-patch --deps dep1 purge@lib1')
    t.grep('Purging lib1')
    t.ngrep('Purging dep1')

    # with --purge:only: the purge@ modules only purged, nothing built
    t.runs('./scbi --no-patch --deps --purge:only purge@lib1 dep1')
    t.grep('Purging lib1')
    t.ngrep('Purging dep1')
    t.ngrep('Building')

    # a parallel build: the workers know the purge@ modules (dep1 not
    # purged with --purge:only)
    t.runs('./scbi --parallel --no-patch --deps purge@lib1 dep1')
    t.grep('Purging lib1')
    t.ngrep('Purging dep1')
    t.ngrep('the build was sequential')
    t.runs('./scbi --parallel --no-patch --deps --purge:only purge@lib1 dep1')
    t.grep('Purging lib1')
    t.ngrep('Purging dep1')
    t.ngrep('Building')

    # a variant: only this one purged (built as a module of the command
    # line), not the default one needed by dep1
    t.runs('./scbi --no-patch --deps purge@lib1/other dep1')
    t.grep('Purging lib1 for .*/other')
    t.ngrep('Purging lib1 for .*/default')
    t.ngrep('Purging dep1')

    # purge@ in a dependency: an error
    t.sh("sed -i 's/- lib1/- purge@lib1/' scripts.d/dep1.yaml")
    t.nruns('./scbi --no-patch --deps dep1')
    t.grep('purge@ is only allowed on the command line')
    t.nruns('./scbi lint scripts.d/dep1.yaml')
    t.grep('purge@ is only allowed on the command line')
