def test(t):
    # --update:prefetch: the git clones and the archives updated ahead by
    # background jobs, the result the same as --update.

    t.sh("""\
mkrepo() {
    (
        mkdir -p .root/repos
        cd .root/repos
        rm -fr $1
        git init -b main $1 &> /dev/null
        cd $1
        git config user.name test
        git config user.email test@example.com
        echo v1 > v.txt
        git add v.txt
        git commit -m v1 &> /dev/null
    )
}
mkplugin() {
    cat > scripts.d/$1.yaml <<END
plugin: $1

vcs:
  proxy: default
  options: none
  protocol: git
  url: \\${TESTREPOS}/$2

build: cat ../src/v.txt

install: echo INSTALL
END
}
mkrepo pfa
mkrepo pfb
mkplugin pfa pfa
mkplugin pfb pfb
mkplugin pfgone does-not-exist
rm -f .root/.archives/dltar-src.tar.bz2*
cp .root/.store/dltar-1-src.tar.bz2 .root/.store/dltar-src.tar.bz2
cp .root/.store/dltar-1-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1
""")

    t.runs("./scbi --update pfa pfb dltar:#0")

    built = """\
xxxx/xx/xx xx:xx:xx : Using cached module plan (xxxxxxxxxxxxxxxxxxxx)

xxxx/xx/xx xx:xx:xx : Building pfa [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building pfa [default] (master)

xxxx/xx/xx xx:xx:xx : Building pfb [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building pfb [default] (master)

xxxx/xx/xx xx:xx:xx : Building dltar [default] (0)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from archive
xxxx/xx/xx xx:xx:xx : extract archive dltar-src.tar.bz2
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building dltar [default] (0)
"""

    # =================== --update: a commit in pfa, another archive

    t.sh("""\
(
    cd .root/repos/pfa
    echo v2 > v.txt
    git commit -a -m v2 &> /dev/null
)
cp .root/.store/dltar-2-src.tar.bz2 .root/.store/dltar-src.tar.bz2
cp .root/.store/dltar-2-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1
""")

    t.runs("./scbi --update pfa pfb dltar:#0")
    t.clean_diff(built)
    t.runs("cat .root/builds/pfa/src/v.txt .root/builds/pfb/src/v.txt")
    t.diff("v2\nv1\n")
    t.runs("grep -a Script .root/builds/dltar/src/script")
    t.grep("Script 2")

    # =================== --update:prefetch: the same, fetched ahead

    t.sh("""\
(
    cd .root/repos/pfa
    echo v3 > v.txt
    git commit -a -m v3 &> /dev/null
)
cp .root/.store/dltar-1-src.tar.bz2 .root/.store/dltar-src.tar.bz2
cp .root/.store/dltar-1-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1
""")

    t.runs("./scbi --update:prefetch pfa pfb dltar:#0")
    t.clean_diff(built)
    t.runs("cat .root/builds/pfa/src/v.txt .root/builds/pfb/src/v.txt")
    t.diff("v3\nv1\n")
    t.runs("grep -a Script .root/builds/dltar/src/script")
    t.grep("Script 1")
    # the work directory of the jobs removed
    t.nok("-d .root/builds/.prefetch")

    # =================== nothing new: nothing rebuilt

    t.runs("./scbi --update:prefetch pfa pfb dltar:#0")
    t.grep("pfa.*no build needed\\|no build needed")
    t.ngrep("extract archive")
    t.ngrep("build starting")

    # =================== a remote not found: the usual error

    t.nruns("./scbi --update:prefetch pfgone")
    t.grep("cannot get sources from")

    # =================== update = prefetch in the ini file

    t.sh("""\
(
    cd .root/repos/pfa
    echo v4 > v.txt
    git commit -a -m v4 &> /dev/null
)
printf '[pf]\\n   update = prefetch\\n   modules = pfa\\n' > .scbi
""")
    t.runs("./scbi --ini=pf")
    t.runs("cat .root/builds/pfa/src/v.txt")
    t.diff("v4\n")
