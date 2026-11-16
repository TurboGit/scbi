def test(t):
    t.sh("""\
GVER=$(gcc --version | grep gcc | awk '{print $4}')
TVER=$(tr --version | grep ^tr | awk '{print $4}')
""")

    # check for auto variant depending on os package with specific version

    t.runs('./scbi mautov2/auto:99.99')

    t.clean_diff(t.text("""\
xxxx/xx/xx xx:xx:xx : mautov2 99.99 using standard variant
xxxx/xx/xx xx:xx:xx :   ↳ gcc $GVER installed
xxxx/xx/xx xx:xx:xx :   ↳ coreutils $TVER used

xxxx/xx/xx xx:xx:xx : Building mautov2 [default] (99.99)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : get sources from git
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : End Building mautov2 [default] (99.99)
"""))
