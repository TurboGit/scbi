def test(t):
    # Check for OS specific function in env scripts

    t.set('LDIR', '.root/builds/osenv/build/logs')

    t.runs('./scbi osenv')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building osenv [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building osenv [default] (n/a)
""")

    # Test that values in build.log are equivalent to env.cmd

    t.grep(*t.words('"BOSENV benv-val"                  $LDIR/build.log'))
    t.grep(*t.words('"PATH /tmp"                        $LDIR/build.log'))
    t.grep(*t.words('"define-var SET BOSENV \\"benv-val" $LDIR/env.cmd'))
    t.grep(*t.words('"define-var ADD PATH \\"/tmp\\""     $LDIR/env.cmd'))

    #  the Windows OS module (testsuite knob), with a fake cygpath
    t.set('SCBI_OS_MODULE', 'windows')
    t.sh("""\
printf '#!/bin/sh\\necho /path/osenv$2\\n' > cygpath
chmod +x cygpath
""")

    t.runs('./scbi -f osenv')

    # Test that values in build.log are transformed but not those in env.cmd

    t.grep(*t.words('"BOSENV benv-val"                  $LDIR/build.log'))
    t.grep(*t.words('"PATH /path/osenv/tmp"             $LDIR/build.log'))
    t.grep(*t.words('"define-var SET BOSENV \\"benv-val" $LDIR/env.cmd'))
    t.grep(*t.words('"define-var ADD PATH \\"/tmp\\""     $LDIR/env.cmd'))

    t.unset('SCBI_OS_MODULE')

    # Test that replaying build.cmd is fully equivalent (the environment
    # recorded with the OS dependant transformations).

    t.runs('./scbi replay $LDIR/build.cmd')

    t.clean_diff("""\
BOSENV benv-val
PATH /path/osenv/tmp
""")

    t.sh('rm -f cygpath')
