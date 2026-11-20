def test(t):
    # scbi lint knows the variables set by the environment file (the one
    # of --env, else the default one).

    t.sh("""\
cat > scripts.d/.env-lintvar.yaml <<'END'
vars:
  VAR: toto
END
cat > scripts.d/lintvar.yaml <<'END'
plugin: lintvar

build-env:
  - set-var LV 9

config-options:
  - -DVAR=${VAR}
  - -DLV=$LV

config: cmake $(config-options) ../src
END
""")

    # =================== VAR unknown without the environment file
    t.runs('./scbi lint lintvar')
    t.grep(r'warning: (config-options) variable VAR is not known in this hook')
    t.ngrep('variable LV')

    # =================== VAR set by the environment file
    t.runs('./scbi --env=lintvar lint lintvar')
    t.ngrep('warning')
