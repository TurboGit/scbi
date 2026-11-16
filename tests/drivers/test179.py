def test(t):
    #  scbi replay --script: a Bash script running a step by hand

    t.set('TVDIR', '.root/builds/test2/x86_64-linux-gnu-default')

    t.runs('./scbi -s -c -b -i test2')

    t.runs('./scbi replay --script $TVDIR/logs/install.cmd')

    t.sh('./scbi replay --script $TVDIR/logs/install.cmd > $TVDIR/install.sh')

    #  only the script on the console, even with --stat

    t.runs('./scbi --stat replay --script $TVDIR/logs/install.cmd')

    t.is_('"$(./scbi --stat replay --script $TVDIR/logs/install.cmd | head -1)"', '==', '"#!/bin/bash"')

    t.runs('grep -E -e "^(PREFIX=|cd |mkdir|cp|#!)" $TVDIR/install.sh')

    #  the parameters and driver variables replaced by their values
    t.clean_diff("""\
#!/bin/bash
cd <pwd>/.root/builds/test2/x86_64-linux-gnu-default/src || exit 1
mkdir -p <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/bin <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/include
cp -r main <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/bin
cp -r incl.h <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/include
""")

    #  --script:inline: a single line, in a sub-shell
    t.runs('./scbi replay --script:inline $TVDIR/logs/install.cmd')
    t.runs("./scbi replay --script:inline $TVDIR/logs/install.cmd | sed -e 's/; export [^;]*;/; export ...;/'")
    t.clean_diff("""\
( cd <pwd>/.root/builds/test2/x86_64-linux-gnu-default/src || exit 1; export ...; mkdir -p <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/bin <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/include; cp -r main <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/bin; cp -r incl.h <pwd>/.root/builds/test2/x86_64-linux-gnu-default/install/include )
""")

    #  the script installs the module again, with an empty environment

    t.sh('rm -fr $TVDIR/install')

    t.runs('env -i /bin/bash $TVDIR/install.sh')

    t.runs('ls $TVDIR/install/bin $TVDIR/install/include')

    t.clean_diff(t.text("""\
$TVDIR/install/bin:
main

$TVDIR/install/include:
incl.h
"""))
