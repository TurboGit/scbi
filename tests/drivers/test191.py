def test(t):
    # scbi lint --json (issues with their position in the file) and
    # --stdin (an unsaved buffer); scbi format --stdin

    t.sh("""\
cat > scripts.d/edit.yaml <<'END'
plugin: edit

config: |-
  CDEBUG = is-enabled cmake-debug
  cmake $NOPE ../src
END
""")

    # =================== lint --json

    t.runs("./scbi --color:no lint --json edit")

    t.clean_diff("""\
[
 {
  "file": "<pwd>/scripts.d/edit.yaml",
  "line": 5,
  "column": 9,
  "level": "warning",
  "hook": "config",
  "message": "variable NOPE is not known in this hook"
 },
 {
  "file": "<pwd>/scripts.d/edit.yaml",
  "line": 4,
  "column": 3,
  "level": "warning",
  "hook": "config",
  "message": "line 1: variable CDEBUG is set but never used"
 }
]
""")

    # =================== lint --json --stdin: the text given, not the file

    t.runs("printf 'plugin: edit\\nbuild: make $NOPE2\\nconfig:\\n' | ./scbi --color:no lint --json --stdin edit")

    t.clean_diff("""\
[
 {
  "file": "<pwd>/scripts.d/edit.yaml",
  "line": 2,
  "column": 13,
  "level": "warning",
  "hook": "build",
  "message": "variable NOPE2 is not known in this hook"
 },
 {
  "file": "<pwd>/scripts.d/edit.yaml",
  "line": 3,
  "column": 1,
  "level": "warning",
  "hook": "config",
  "message": "defined but empty"
 }
]
""")

    # =================== an error: exit status 1

    t.nruns("printf 'plugin: edit\\nout-of-tree: maybe\\n' | ./scbi --color:no lint --json --error --stdin edit")

    t.grep('"level": "error"')
    t.grep('"line": 2')

    # =================== format --stdin

    t.runs("printf 'config: |-\\n  make\\nplugin: edit\\n' | ./scbi --color:no format --stdin edit")

    t.diff("""\
plugin: edit

config: make
""")

    # the file is not changed
    t.runs("cat scripts.d/edit.yaml")

    t.grep("CDEBUG = is-enabled cmake-debug")
