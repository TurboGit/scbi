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

    # =================== the order of the keys does not count: hooks,
    # variables, functions and qualifiers reversed, no rebuild
    t.sh("printf 'vars:\\n  RSHA_A: a\\n  RSHA_B: b\\n\\nfunctions:\\n  rsha-f1:\\n    run: echo 1\\n"
         "  rsha-f2:\\n    run: echo 2\\n' >> scripts.d/rsha.yaml")
    t.runs('./scbi lint --error scripts.d/rsha.yaml')
    t.runs('./scbi rsha')
    t.grep('trigger: build not up-to-date')
    t.sh('''python3 - scripts.d/rsha.yaml scripts.d/rshabase.yaml <<'PY'
import sys, yaml
def rev(x):
    if isinstance(x, dict):
        return {k: rev(v) for k, v in reversed(list(x.items()))}
    if isinstance(x, list):
        return [rev(v) for v in x]
    return x
for path in sys.argv[1:]:
    data = yaml.safe_load(open(path))
    open(path, "w").write(yaml.safe_dump(rev(data), sort_keys=False))
PY''')
    t.runs('./scbi lint --error scripts.d/rsha.yaml scripts.d/rshabase.yaml')
    t.sh('head -3 scripts.d/rsha.yaml > $TEST_OUTPUT')
    t.ngrep('^plugin:')
    t.runs('./scbi rsha')
    t.grep('no build needed: versions matching')
    t.ngrep('trigger: ')

    # =================== the order of the dependencies does not count
    t.sh("sed -i 's/^  - rsha$/  - rsha\\n  - depA/' scripts.d/rshadep.yaml")
    t.runs('./scbi --deps rshadep')
    t.grep('trigger: ')
    t.sh("sed -i '/^  - rsha$/d; s/^  - depA$/  - depA\\n  - rsha/' scripts.d/rshadep.yaml")
    t.sh('grep -A2 "^depends:" scripts.d/rshadep.yaml > $TEST_OUTPUT')
    t.diff("""\
depends:
  - depA
  - rsha
""")
    t.runs('./scbi --deps rshadep')
    t.ngrep('trigger: ')
    t.grep('Building rshadep')
