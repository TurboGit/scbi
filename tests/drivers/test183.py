def test(t):
    # The build id uses the plug-in resolved for the module reference:
    # comments, formatting, other variants, unused hooks and the env hook
    # of the module do not rebuild it; the hooks used, the functions and
    # the env of its dependencies do.

    def built(module):
        t.grep(f': Building {module} ')
        t.grep('trigger: ')
        t.ngrep('no build needed')

    def not_built():
        t.grep('no build needed: versions matching')
        t.ngrep('trigger: ')

    t.runs('./scbi rsha')
    built('rsha')

    # =================== a comment, the formatting: no rebuild
    t.sh('sed -i "1i #  a comment" scripts.d/rsha.yaml')
    t.sh("sed -i 's/^config: echo rsha$/config: \"echo rsha\"/' scripts.d/rsha.yaml")
    t.runs('./scbi rsha')
    not_built()

    # =================== a variant, a guard for it: no rebuild
    t.sh("sed -i 's/^config: \"echo rsha\"$/config:\\n  _: echo rsha\\n  other: echo other/' scripts.d/rsha.yaml")
    t.sh('printf "build-env:\\n  - if variant == other: set-var RSHA_X 1\\n" >> scripts.d/rsha.yaml')
    t.runs('./scbi lint --error scripts.d/rsha.yaml')
    t.runs('./scbi rsha')
    not_built()
    t.runs('./scbi rsha/other')
    built('rsha')

    # =================== its own build-env used: rebuild
    t.sh('echo "  - set-var RSHA_Y 1" >> scripts.d/rsha.yaml')
    t.runs('./scbi rsha')
    built('rsha')

    # =================== parent: the hook of another variant, no rebuild;
    # the hook used, rebuild
    t.sh("sed -i 's/echo install other/echo install other2/' scripts.d/rshabase.yaml")
    t.runs('./scbi rsha')
    not_built()
    t.sh("sed -i 's/_: echo install$/_: echo install2/' scripts.d/rshabase.yaml")
    t.runs('./scbi rsha')
    built('rsha')

    # =================== a hook of the module, a function of the parent
    t.sh("sed -i 's/_: echo rsha$/_: echo rsha2/' scripts.d/rsha.yaml")
    t.runs('./scbi rsha')
    built('rsha')
    t.sh("sed -i 's/echo helper/echo helper2/' scripts.d/rshabase.yaml")
    t.runs('./scbi rsha')
    built('rsha')

    # =================== env: rebuilds the dependents, not the module
    t.runs('./scbi --deps rshadep')
    t.grep('trigger: not yet built')
    t.sh("sed -i 's/^  - set-var RSHA_ROOT \\$PREFIX$/  - set-var RSHA_ROOT $PREFIX\\n  - set-var RSHA_Z 1/' "
         "scripts.d/rsha.yaml")
    t.runs('./scbi lint --error scripts.d/rsha.yaml')
    t.runs('./scbi --deps rshadep')
    t.sh('grep -o ": Building [a-z]*\\|no build needed\\|trigger: [a-z -]*" $TEST_OUTPUT > out; mv out $TEST_OUTPUT')
    t.diff("""\
: Building rsha
no build needed
: Building rshadep
trigger: build not up-to-date
""")

    # =================== env item for another variant: no rebuild at all
    t.sh("sed -i 's/^  - set-var RSHA_Z 1$/  - set-var RSHA_Z 1\\n  - if variant == other: set-var RSHA_W 1/' "
         "scripts.d/rsha.yaml")
    t.runs('./scbi --deps rshadep')
    t.ngrep('trigger: ')
