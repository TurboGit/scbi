def test(t):
    # IS_AGGREGATED in the module-final-step: in a direct aggregate only
    # the modules of the meta-module are aggregated, not their
    # dependencies; in a recursive aggregate the dependencies are too.
    # The build dependencies of a meta-module are never aggregated.

    # =================== direct: mainlib aggregated, not its dependency lib1
    t.runs('./scbi --env=packaging --deps metaagg3/agg')
    t.grep('^R m:mainlib v:default d:default m:no a:direct i:no$')
    t.grep('^R m:lib1 v:default d:default m:no a:no i:no$')
    t.grep('^R m:metaagg3 v:agg d:default m:aggregate a:no i:no$')

    # =================== recursive: the dependencies are aggregated too
    t.runs('./scbi --env=packaging --deps --force metaagg4')
    t.grep('^R m:mainlib v:default d:default m:no a:recursive i:')
    t.grep('^R m:lib1 v:default d:default m:no a:recursive i:')
    t.grep('^R m:metaagg4 v:default d:default m:aggregate a:no i:')

    # =================== build-depends of an aggregate: not aggregated
    t.runs('./scbi --env=packaging --deps metaaggbd')
    t.grep('^R m:lib1 v:default d:build m:no a:no i:')
    t.grep('^R m:lib2 v:default d:default m:no a:direct i:')
    t.grep('^R m:metaaggbd v:default d:default m:aggregate a:no i:')
