def test(t):
    #  Check env & build-env variants

    t.set('VDIR', '.root/builds/varenv/build/logs/build.log')
    t.set('MDIR', '.root/builds/varenvmain/build/logs/build.log')

    t.runs('./scbi --deps varenvmain')

    t.grep(*t.words('"^VENV NONE:default:common"  $MDIR'))
    t.ngrep(*t.words('"^VENV NONE:default:common"  $VDIR'))
    t.grep(*t.words('"^VBENV NONE:default:common" $VDIR'))

    t.runs('./scbi --deps varenv/another varenvmain')

    t.grep(*t.words('"^VENV another:common"  $MDIR'))
    t.grep(*t.words('"^VBENV another:common" $VDIR'))

    t.runs('./scbi --deps varenv/another.fast varenvmain')

    t.grep(*t.words('"^VENV another:common"  $MDIR'))
    t.grep(*t.words('"^VBENV fast:another:common" $VDIR'))
