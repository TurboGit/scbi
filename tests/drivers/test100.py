def test(t):
    t.set('SCBI_INI_FILE', '$ROOTDIR/.scbiini')

    t.sh("""\
cat <<EOF > $SCBI_INI_FILE
[sc]
   setup = yes
   config = yes
   build = no
   install = no
   wrapup = no

[full]
   update = yes
   force = yes

[common]
   modules = test2
EOF
""")

    t.runs('./scbi --ini=sc')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test2 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : End Building test2 [default] (master)
""")

    t.runs('./scbi --ini=full')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building test2 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building test2 [default] (master)
""")

    t.sh("""\
cat <<EOF > $SCBI_INI_FILE

stat = yes

[sc]
   setup = yes
   config = yes
   build = no
   install = no
   wrapup = no

[full]
   update = yes
   force = yes

[common]
   modules = test2
EOF
""")

    t.runs('./scbi lib1')

    #  Filter out some OS dependent stat to have a stable output
    t.set('TMP', '$(mktemp)')
    # to clear discriminants we need to remove all lines starting
    # with indentation.
    t.sh("""\
cat $TEST_OUTPUT |
grep -v ^discriminants |
grep -v "^                        " |
grep -v platforms |
grep -v ^host |
grep -v SVN > $TMP
mv $TMP $TEST_OUTPUT
""")

    t.clean_diff("""\
SCBI : @VERSION@

stats
-----
build dir             : <pwd>/.root/builds
install prefix        : <pwd>/.root/builds/install
archive dir           : <pwd>/.root/.archives
patches dir           : <pwd>/.root/.patches
user's Git repository : <pwd>/.root/git
plug-ins dir          : <pwd>/scripts.d
plan                  : no
e-mail notification   : no

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : apply patch lib1-0-fix.patch
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)
""")

    t.sh("""\
rm -f $SCBI_INI_FILE
unset SCBI_INI_FILE
""")
