def test(t):
    # Without --update the git repository is not fetched (a new commit of
    # the remote is not used); with --update it is.

    t.sh("""\
(
    mkdir -p .root/repos
    cd .root/repos
    rm -fr gitupd
    git init -b main gitupd &> /dev/null
    cd gitupd
    git config user.name test
    git config user.email test@example.com
    echo v1 > v.txt
    git add v.txt
    git commit -m v1 &> /dev/null
)
cat > scripts.d/gitupd.yaml <<'END'
plugin: gitupd

vcs:
  proxy: default
  options: none
  protocol: git
  url: ${TESTREPOS}/gitupd

build: cat ../src/v.txt

install: echo INSTALL
END
""")

    t.runs("./scbi gitupd")
    t.runs("cat .root/builds/gitupd/src/v.txt")
    t.diff("v1\n")

    # a new commit in the remote
    t.sh("""\
(
    cd .root/repos/gitupd
    echo v2 > v.txt
    git commit -a -m v2 &> /dev/null
)
""")

    # =================== without --update: the old commit

    t.runs("./scbi gitupd")
    t.runs("cat .root/builds/gitupd/src/v.txt")
    t.diff("v1\n")
    t.runs("git --git-dir=.root/builds/.vcs/gitupd/.git log --oneline origin/main | wc -l")
    t.diff("1\n")

    # =================== with --update: the new one

    t.runs("./scbi --update gitupd")
    t.runs("cat .root/builds/gitupd/src/v.txt")
    t.diff("v2\n")
