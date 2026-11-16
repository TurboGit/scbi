def test(t):
    # check for local plan
    #

    t.runs('./scbi --purge:only lib1')
    t.runs('./scbi --purge:only lib2')

    t.sh("""\
(
    mkdir -p .root/git
    cd .root/git
    rm -fr lib2.bundle
    git clone ../repos/lib2.bundle lib2.bundle &> /dev/null
    sed -i 's/libb.B master/libb.B next version/g' ./lib2.bundle/lib2.c
)
""")

    # echo ========== build supermod
    t.runs('./scbi --no-patch --tests --deps supermod')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule supermod [default] setup
xxxx/xx/xx xx:xx:xx : setup starting
xxxx/xx/xx xx:xx:xx : setup completed
xxxx/xx/xx xx:xx:xx : End metamodule supermod [default] setup

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ supermod
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.C master
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (master)

xxxx/xx/xx xx:xx:xx : Building lib2 [default] (master)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ supermod
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
libb.B master (default)
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [default] (master)

xxxx/xx/xx xx:xx:xx : Metamodule supermod [default] wrapup
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : End metamodule supermod [default] wrapup
""")

    # echo ========== build supermod with local plan myplan
    t.sh("""\
echo lib1:v1 > .scbi-plan-myplan
echo lib2:dev >> .scbi-plan-myplan
""")
    t.runs('./scbi --no-patch --tests --plan=myplan --deps supermod')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule supermod [default] setup
xxxx/xx/xx xx:xx:xx : setup starting
xxxx/xx/xx xx:xx:xx : setup completed
xxxx/xx/xx xx:xx:xx : End metamodule supermod [default] setup

xxxx/xx/xx xx:xx:xx : Building lib1 [default] (v1)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ supermod
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
liba.A br_a
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib1 [default] (v1)

xxxx/xx/xx xx:xx:xx : Building lib2 [default] (dev)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ supermod
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
main
libb.B next version (default)
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building lib2 [default] (dev)

xxxx/xx/xx xx:xx:xx : Metamodule supermod [default] wrapup
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx :   ↳ lib1 changed
xxxx/xx/xx xx:xx:xx :   ↳ lib2 changed
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : End metamodule supermod [default] wrapup
""")

    t.sh('rm .scbi-plan-myplan')
