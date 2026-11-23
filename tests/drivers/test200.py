def test(t):
    # A failing hook prints the log command messages once: they are
    # already on the console, not again from the tail of the step log.

    t.nruns('./scbi logfail')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building logfail [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : pre-setup starting
xxxx/xx/xx xx:xx:xx :   logfail is only meant to be used in cross mode
xxxx/xx/xx xx:xx:xx : logfail (FAILED) pre-setup failed with error 1
""")
