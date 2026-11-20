def test(t):
    # scbi ini: the sections of the ini files (for the editors)

    t.sh("""\
cat > .scbi <<'END'
jobs = 2

[common]
   jobs = 4

[libs]
   modules = lib1 lib2

[app]
   modules = app
   run = app --version

[scbi-show]
   stat = no
END
""")

    t.runs("./scbi --color:no ini")

    t.diff("""\
libs                 modules: lib1 lib2
app                  run: app --version
""")

    t.runs("./scbi --color:no ini --json")

    t.clean_diff("""\
[
 {
  "name": "libs",
  "file": "<pwd>/.scbi",
  "modules": "lib1 lib2",
  "run": "",
  "tests": ""
 },
 {
  "name": "app",
  "file": "<pwd>/.scbi",
  "modules": "app",
  "run": "app --version",
  "tests": ""
 }
]
""")
