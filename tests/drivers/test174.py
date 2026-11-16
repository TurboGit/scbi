def test(t):
    # scbi lint on YAML plug-ins

    t.runs('./scbi lint fixtures/lint/lintok.yaml')

    t.clean_diff("""\

========== Handle fixtures/lint/lintok.yaml
""")

    t.nruns('./scbi lint fixtures/lint/lintbad.yaml')

    t.clean_diff("""\

========== Handle fixtures/lint/lintbad.yaml
   error:   (vcs) missing fields ['protocol', 'url']
   error:   (confg) unknown hook 'confg', did you mean 'config'?
   warning: (depends.v1) defined but empty
   error:   (config.common) 'common' is only allowed for cumulative hooks
   warning: (config.v1) VERSION is a parameter of archive, not of config
   warning: (build) variable UNKNOWN_VAR is not known in this hook
   error:   (env) unknown environment action 'frob-var'
   warning: (env) variable OTHER is not known in this hook
   error:   (out-of-tree) 'maybe' is not one of true/false
   error:   (patches) unexpected end of condition: 'ref =='
""")

    t.nruns('./scbi lint --error fixtures/lint/lintbad.yaml')

    t.clean_diff("""\
   error:   (vcs) missing fields ['protocol', 'url']
   error:   (confg) unknown hook 'confg', did you mean 'config'?
   error:   (config.common) 'common' is only allowed for cumulative hooks
   error:   (env) unknown environment action 'frob-var'
   error:   (out-of-tree) 'maybe' is not one of true/false
   error:   (patches) unexpected end of condition: 'ref =='
""")

    t.runs('./scbi lint nothere')

    t.clean_diff("""\

========== Skip nothere: not found
""")
