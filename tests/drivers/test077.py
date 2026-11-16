def test(t):
    # test for build-depends and depends environment

    t.set('L0DIR', '.root/builds/lvl0/build/logs/build.log')
    t.set('L1DIR', '.root/builds/lvl1/build/logs/build.log')
    t.set('L2DIR', '.root/builds/lvl2/build/logs/build.log')
    t.set('L3DIR', '.root/builds/lvl3/build/logs/build.log')

    ####################

    t.runs('./scbi --deps lvl0')

    t.grep(*t.words('"00 build-zerox" $L0DIR'))
    t.grep(*t.words('"01 onex" $L0DIR'))
    t.grep(*t.words('"02 twox" $L0DIR'))
    t.grep(*t.words('"03 x" $L0DIR'))
    t.grep(*t.words('"04 x" $L0DIR'))

    ####################

    t.runs('./scbi --deps lvl1')

    t.grep(*t.words('"10 x" $L1DIR'))
    t.grep(*t.words('"11 x" $L1DIR'))
    t.grep(*t.words('"12 twox" $L1DIR'))
    t.grep(*t.words('"13 threex" $L1DIR'))
    t.grep(*t.words('"14 x" $L1DIR'))

    ####################

    t.runs('./scbi --deps lvl2')

    t.grep(*t.words('"20 x" $L2DIR'))
    t.grep(*t.words('"21 x" $L2DIR'))
    t.grep(*t.words('"22 x" $L2DIR'))
    t.grep(*t.words('"23 x" $L2DIR'))
    t.grep(*t.words('"24 fourx" $L2DIR'))

    ####################

    t.runs('./scbi --deps lvl3')

    t.grep(*t.words('"30 x" $L3DIR'))
    t.grep(*t.words('"31 x" $L3DIR'))
    t.grep(*t.words('"32 x" $L3DIR'))
    t.grep(*t.words('"33 build-threex" $L3DIR'))
    t.grep(*t.words('"34 x" $L3DIR'))
