def test(t):
    #  Dependencies of a meta-module with common modules (modules hook of
    #  the common and default variants): dep1 depends on lib1

    t.runs('./scbi metadeps')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Metamodule metadeps [default] setup
xxxx/xx/xx xx:xx:xx : End metamodule metadeps [default] setup

xxxx/xx/xx xx:xx:xx : Metamodule metadeps [default] wrapup
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : wrapup completed
xxxx/xx/xx xx:xx:xx : End metamodule metadeps [default] wrapup
""")

    t.runs('./scbi show --depends metadeps')

    t.diff("""\
dep1
lib1
metadeps
""")
