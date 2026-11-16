def test(t):
    # Check SCBI_MODULES_DIRS for out-of-tree

    t.runs('./scbi lib3 oot')

    t.set('LOG', '.root/builds/lib3/build/logs/env.cmd')

    t.grep(*t.words('"lib3@src.*src" $LOG'))
    t.grep(*t.words('"lib3@build.*src" $LOG'))
    t.grep(*t.words('"lib3.*install" $LOG'))

    t.set('LOG', '.root/builds/oot/build/logs/env.cmd')

    t.grep(*t.words('"oot@src.*src" $LOG'))
    t.grep(*t.words('"oot@build.*build" $LOG'))
    t.grep(*t.words('"oot.*install" $LOG'))
