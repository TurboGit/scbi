def test(t):
    t.set('EFILE', '.root/builds/testme/build/logs/env.cmd')

    t.runs('./scbi --deps testme')

    t.grep(*t.words('"^# gentool" $EFILE'))
    t.grep(*t.words('"^define-var ADD PATH " $EFILE'))

    t.grep(*t.words('"^# testme" $EFILE'))

    # check SCBI_MODULES_DIR entries
    t.grep(*t.words('\'\\["testme"\\]\' $EFILE'))
    t.grep(*t.words('\'\\["gentool"\\]\' $EFILE'))

    t.grep(*t.words('\'\\["testme@src"\\]\' $EFILE'))
    t.grep(*t.words('\'\\["testme@build"\\]\' $EFILE'))
    t.grep(*t.words('\'\\["gentool@src"\\]\' $EFILE'))
    t.grep(*t.words('\'\\["gentool@build"\\]\' $EFILE'))
