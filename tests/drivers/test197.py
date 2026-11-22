def test(t):
    # source-tree: exclude (paths from the root of the sources of the
    # entry, not copied, kept in the tree), the module itself by its name.

    t.sh("""\
mkrepo() {
    (
        mkdir -p .root/repos
        cd .root/repos
        rm -fr $1
        git init -b main $1 &> /dev/null
        cd $1
        git config user.name test
        git config user.email test@example.com
        shift
        for f in "$@"; do
            mkdir -p $(dirname $f)
            echo $(basename $f) > $f
        done
        git add .
        git commit -m init &> /dev/null
    )
}
mkrepo tbase README docs/manual.txt src/a.c src/docs/keep.txt tests/old/x.t tests/new/y.t
mkrepo texcl m.c notes/todo.txt

cat > scripts.d/tbase.yaml <<'END'
plugin: tbase

vcs:
  proxy: default
  options: none
  protocol: git
  url: ${TESTREPOS}/tbase

build: echo tbase

install: echo INSTALL
END

cat > scripts.d/texcl.yaml <<'END'
plugin: texcl

vcs:
  proxy: default
  options: none
  protocol: git
  url: ${TESTREPOS}/texcl

source-tree:
  - from: tbase
    exclude:
      - docs
      - tests/old
  - from: texcl
    to: src/mod
    exclude:
      - notes

depends:
  - tbase

build: echo BUILD

install: echo INSTALL
END
""")

    t.set("TREE", ".root/builds/texcl/x86_64-linux-gnu-default/src")

    t.runs("./scbi --deps texcl")

    # docs and tests/old of tbase not copied (src/docs kept: the paths are
    # from the root of the sources), notes of texcl not copied (from the
    # root of its sources, not of the tree), texcl (by its name) in src/mod
    t.runs("cd $TREE && find . -type f | sort")
    t.diff("""\
./README
./src/a.c
./src/docs/keep.txt
./src/mod/m.c
./tests/new/y.t
""")

    # =================== the excluded paths are kept in the tree

    t.sh("""\
mkdir -p $TREE/docs $TREE/tests/old $TREE/src/mod/notes
echo local > $TREE/docs/local.txt
echo local > $TREE/tests/old/local.t
echo local > $TREE/src/mod/notes/local.txt
( cd .root/repos/tbase && echo b.c > src/b.c && git add src/b.c && git commit -q -m b )
""")
    t.runs("./scbi --deps --update texcl")
    t.runs("cd $TREE && find . -type f | sort")
    t.diff("""\
./README
./docs/local.txt
./src/a.c
./src/b.c
./src/docs/keep.txt
./src/mod/m.c
./src/mod/notes/local.txt
./tests/new/y.t
./tests/old/local.t
""")

    # the module by its name: no lint error
    t.runs("./scbi --color:no lint texcl")
    t.ngrep("source-tree")
