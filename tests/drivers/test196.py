def test(t):
    # source-tree: the sources of three modules combined as in p-gnat
    # (gcc + tada in gcc/ada + gcc-interface in gcc/ada/gcc-interface).

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
mkrepo tgcc README gcc/main.c gcc/ada/old.adb gcc/testsuite/ada/acats.adb
mkrepo tada ali.adb sem.adb
mkrepo tgcciface trans.c misc.c

mksrc() {
    cat > scripts.d/$1.yaml <<END
plugin: $1

vcs:
  proxy: default
  options: none
  protocol: git
  url: \\${TESTREPOS}/$1

build: echo $1

install: echo INSTALL
END
}
mksrc tgcc
mksrc tgcciface

cat > scripts.d/tada.yaml <<'END'
plugin: tada

vcs:
  proxy: default
  options: none
  protocol: git
  url: ${TESTREPOS}/tada

patches:
  - tada.diff

source-tree:
  - from: tgcc
  - to: gcc/ada
  - from: tgcciface
    to: gcc/ada/gcc-interface

depends:
  - tgcc
  - tgcciface

build: echo BUILD

install: echo INSTALL
END

mkdir -p scripts.d/patches
cat > scripts.d/patches/tada.diff <<'END'
--- a/ali.adb
+++ b/ali.adb
@@ -1 +1,2 @@
 ali.adb
+patched
END
""")

    t.set("TREE", ".root/builds/tada/x86_64-linux-gnu-default/src")

    t.runs("./scbi --deps tada")

    # gcc at the top, gnat in gcc/ada (the old gcc/ada replaced, gcc/testsuite/ada
    # kept), gcc-interface inside it, no .git, the patch applied in gcc/ada
    t.runs("cd $TREE && find . -type f -o -type d -name .git | sort")
    t.diff("""\
./README
./gcc/ada/ali.adb
./gcc/ada/gcc-interface/misc.c
./gcc/ada/gcc-interface/trans.c
./gcc/ada/sem.adb
./gcc/main.c
./gcc/testsuite/ada/acats.adb
""")
    t.runs("cat $TREE/gcc/ada/ali.adb")
    t.diff("ali.adb\npatched\n")

    # =================== files removed upstream: removed from the tree

    t.runs("stat -c %Y $TREE/gcc/main.c > mtime.txt")
    t.sh("""\
( cd .root/repos/tgcc && git rm -q README && git commit -q -m rm )
( cd .root/repos/tada && git rm -q sem.adb && git commit -q -m rm )
( cd .root/repos/tgcciface && git rm -q misc.c && git commit -q -m rm )
""")
    t.runs("./scbi --deps --update tada")
    t.runs("cd $TREE && find . -type f | sort")
    t.diff("""\
./gcc/ada/ali.adb
./gcc/ada/gcc-interface/trans.c
./gcc/main.c
./gcc/testsuite/ada/acats.adb
""")
    # an unchanged file keeps its time
    t.runs("stat -c %Y $TREE/gcc/main.c | diff - mtime.txt")

    # =================== from: not a dependency

    t.sh("""\
sed -e 's/plugin: tada/plugin: tgbad/' -e '/^depends:/,/^$/d' scripts.d/tada.yaml > scripts.d/tgbad.yaml
cat >> scripts.d/tgbad.yaml <<'END'

depends:
  - tgcciface
END
""")
    t.nruns("./scbi tgbad")
    t.grep("source-tree: tgcc is not a dependency (depends, build-depends)")
    t.nruns("./scbi --color:no lint tgbad")
    t.grep(r"error:   (source-tree) tgcc is not a dependency (depends, build-depends)")
    t.runs("./scbi --color:no lint tada")
    t.ngrep("source-tree")

    # only a dependency of another variant: an error for this one
    t.sh("""\
sed -e 's/plugin: tada/plugin: tgvar/' -e '/^depends:/,/^$/d' scripts.d/tada.yaml > scripts.d/tgvar.yaml
cat >> scripts.d/tgvar.yaml <<'END'

depends:
  _:
    - tgcciface
  other:
    - tgcc
    - tgcciface
END
""")
    t.nruns("./scbi tgvar")
    t.grep("source-tree: tgcc is not a dependency (depends, build-depends)")
    t.runs("./scbi --deps tgvar/other")
    t.runs("cat .root/builds/tgvar/x86_64-linux-gnu-other/src/gcc/main.c")
    t.diff("main.c\n")
