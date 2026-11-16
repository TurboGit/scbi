def test(t):
    t.runs('./scbi inh-specific-name')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building inh-specific-name [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : post-install starting
xxxx/xx/xx xx:xx:xx : post-install completed
xxxx/xx/xx xx:xx:xx : End Building inh-specific-name [default] (n/a)
""")

    t.runs("grep -h '@@@' .root/builds/.logs/*inh-specific-name*.log")

    t.clean_diff("""\
@@@ BUILD-inh-specific-name
@@@ CONFIG-inh-specific-name
@@@ POST-INSTALL-inh-specific-name
@@@ POST-INSTALL-postinst
@@@ POST-INSTALL-postinst
""")
