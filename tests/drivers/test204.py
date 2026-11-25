def test(t):
    # A refused copy/delete/delete-tree (outside the sandbox) is an error
    # of the plug-in: the hook stops at once and the step fails, the
    # message on the console (not only in the step log).

    t.sh("""\
cat > scripts.d/refcopy.yaml <<'END'
plugin: refcopy

config: echo config

wrapup: |-
  copy /etc/hostname host || echo never
  echo never
END
cat > scripts.d/refdel.yaml <<'END'
plugin: refdel

config: echo config

wrapup: |-
  mkdir -p d
  delete d
  echo never
END
""")

    t.nruns('./scbi refcopy')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building refcopy [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : config starting
xxxx/xx/xx xx:xx:xx : config completed
xxxx/xx/xx xx:xx:xx : wrapup starting
xxxx/xx/xx xx:xx:xx : refcopy (FAILED) refcopy.yaml: wrapup: line 6: copy: '/etc/hostname' (/etc/hostname) is not in the sandbox <pwd>/.root/builds or the plug-ins directory <pwd>/scripts.d, nothing copied
refcopy.yaml: wrapup: line 6: copy: '/etc/hostname' (/etc/hostname) is not in the sandbox <pwd>/.root/builds or the plug-ins directory <pwd>/scripts.d, nothing copied
xxxx/xx/xx xx:xx:xx : refcopy (FAILED) wrapup failed with error 1
""")
    # (the second line: the output of the step, on the console for the
    # tests only) the message in the step log too, nothing run after the refusal
    t.sh('cat .root/builds/refcopy/x86_64-linux-gnu-default/logs/wrapup.log > $TEST_OUTPUT')
    t.grep("copy: '/etc/hostname'")
    t.ngrep("never")

    t.nruns('./scbi refdel')
    t.grep("refdel (FAILED) refdel.yaml: wrapup: line 7: delete: 'd' is a directory"
           " (use delete-tree), nothing deleted")
    t.grep("refdel (FAILED) wrapup failed with error 1")
    t.ngrep("never")
