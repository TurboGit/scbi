def test(t):
    t.runs('./scbi test37')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test37 [default] (n/a)
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
xxxx/xx/xx xx:xx:xx : End Building test37 [default] (n/a)
""")

    #  the plug-in files
    t.ok('-f .root/builds/test37/build/logs/test37.yaml')
    t.ok('-f .root/builds/test37/build/logs/test17.yaml')

    t.runs('cat .root/builds/.logs/*test37*config.log')

    t.clean_diff("""\
in config (overriding)
# ROOT_DIR /this/is/it
# ABC_ROOT /perfect/here
# PATH     /var:/tmp:/bin:/usr/bin
# CONF17   two:one
""")

    t.runs('cat .root/builds/.logs/*test37*build.log')

    t.clean_diff("""\
in build
ROOT_DIR /this/is/it
ABC_ROOT /perfect/here
PATH     /var:/tmp:/bin:/usr/bin
CONF17   two:one
""")

    t.runs('cat .root/builds/.logs/*test37*install.log')

    t.clean_diff("""\
in install (overriding)
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

    t.runs('source .root/builds/test37/build/logs/env.cmd')

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

    # check out of tree build
    t.nok('-h .root/builds/test37/build/build')
