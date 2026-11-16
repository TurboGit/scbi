def test(t):
    t.runs('./scbi test17')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test17 [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : setup starting
xxxx/xx/xx xx:xx:xx : setup completed
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building test17 [default] (n/a)
""")

    t.runs('cat .root/builds/.logs/*test17*config.log')

    t.clean_diff("""\
in config
ROOT_DIR /this/is/it
ABC_ROOT /perfect/here
PATH     /var:/tmp:/bin:/usr/bin
CONF17   two:one
""")

    t.runs('cat .root/builds/.logs/*test17*build.log')

    t.clean_diff("""\
in build
ROOT_DIR /this/is/it
ABC_ROOT /perfect/here
PATH     /var:/tmp:/bin:/usr/bin
CONF17   two:one
""")

    t.runs('cat .root/builds/.logs/*test17*install.log')

    t.clean_diff("""\
in install
ROOT_DIR /this/is/it
ABC_ROOT /perfect/here
PATH     /var:/tmp:/bin:/usr/bin
CONF17   two:one
""")

    t.sh("""\
function define-var()
{
    local ACTION=$1
    local VAR=$2
    local VALUE=$3

    echo $ACTION $VAR $VALUE
}
declare -fx define-var
""")

    # In driver:
    t.set('OLDPATH', '$PATH')
    t.set('PATH', '/bin:/usr/bin')

    t.runs('source .root/builds/test17/build/logs/env.cmd')

    t.set('PATH', '$OLDPATH')

    t.clean_diff("""\
ADD ROOT_DIR /this/is/it
ADD ROOT_DIR /this/is/it
ADD ROOT_DIR /this/is/it
ADD PATH /tmp
ADD ABC_ROOT /perfect/here
ADD CONF17 one
ADD CONF17 two
ADD PATH /usr/bin
ADD PATH /var
""")
