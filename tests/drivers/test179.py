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

    t.clean_diff(t.text("""\
#!/bin/bash
PREFIX=<pwd>/.root/builds/test2/x86_64-linux-gnu-default/install
cd <pwd>/.root/builds/test2/x86_64-linux-gnu-default/src || exit 1
mkdir -p "\\$PREFIX"/bin "\\$PREFIX"/include
cp -r main "\\$PREFIX"/bin
cp -r incl.h "\\$PREFIX"/include
"""))

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
