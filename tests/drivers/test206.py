def test(t):
    # --check-deps: a module using the files of a module of the sandbox
    # which is not one of its dependencies is reported

    t.sh('''cat > scripts.d/undecl.yaml <<'XEOF'
plugin: undecl

depends:
  ok:
    - lib1

build: |-
  write main.d:
      main.o: $SCBI_PREFIX/include/lib1.h /usr/include/stdio.h
XEOF''')

    t.runs('./scbi lib1')

    # not checked by default
    t.runs('./scbi undecl')
    t.ngrep('not a dependency')

    t.runs('./scbi --check-deps --force undecl')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building undecl [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: forced
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : warning: uses lib1, not a dependency: <sandbox>/install/include/lib1.h
xxxx/xx/xx xx:xx:xx : End Building undecl [default] (n/a)
""")

    # a dependency: nothing reported
    t.runs('./scbi --check-deps undecl/ok')
    t.ngrep('not a dependency')

    # an error with :error
    t.nruns('./scbi --check-deps:error --force undecl')
    t.grep('error: uses lib1, not a dependency')
