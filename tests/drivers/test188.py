def test(t):
    # scbi lint knows the variables set by the env hooks of the
    # dependencies (recursively, through a meta-module and an inherited
    # plug-in too) and by the inherited plug-ins.

    t.sh("""\
cat > scripts.d/lintdep.yaml <<'END'
plugin: lintdep

env:
  - set-var DEP 77
END
cat > scripts.d/lintdep2.yaml <<'END'
plugin: lintdep2

inherit:
  - from: lintdepbase

depends:
  - lintdep
END
cat > scripts.d/lintdepbase.yaml <<'END'
plugin: lintdepbase

env:
  - set-var DEPBASE 1
END
cat > scripts.d/lintmeta.yaml <<'END'
plugin: lintmeta

modules:
  - lintdep2
END
cat > scripts.d/lintparent.yaml <<'END'
plugin: lintparent

vars:
  PVAR: p

build-env:
  - set-var PENV 2
END
cat > scripts.d/lintmain.yaml <<'END'
plugin: lintmain

inherit:
  - from: lintparent

depends:
  - lintmeta

build-env:
  - set-var LV 9

config-options:
  - -DLV=$LV
  - -DDEP=$DEP
  - -DDEPBASE=$DEPBASE
  - -DPVAR=$PVAR
  - -DPENV=$PENV
  - -DOTHER=$OTHER

config: cmake $(config-options) ../src
END
""")

    t.runs('./scbi lint lintmain')
    t.grep(r'warning: (config-options) variable OTHER is not known in this hook')
    t.ngrep('variable \\(LV\\|DEP\\|DEPBASE\\|PVAR\\|PENV\\) ')
    t.sh('grep -c warning $TEST_OUTPUT > out; mv out $TEST_OUTPUT')
    t.diff("1\n")

    # =================== the build-env of a dependency is not given to
    # the modules depending on it
    t.sh("sed -i 's/^env:$/build-env:/' scripts.d/lintdep.yaml")
    t.runs('./scbi lint lintmain')
    t.grep('variable DEP is not known')
