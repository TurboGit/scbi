def test(t):
    # vars: a list value, a word per item in the command hooks, expanded
    # in each hook; += in a hook only for this hook.

    t.sh("""\
(
    mkdir -p .root/repos
    cd .root/repos
    rm -fr tlv
    git init -b main tlv &> /dev/null
    cd tlv
    git config user.name test
    git config user.email test@example.com
    echo src > src.txt
    git add src.txt
    git commit -m init &> /dev/null
)
cat > scripts.d/tlv.yaml <<'END'
plugin: tlv

vars:
  GOPTS:
    - -XBUILD=PROD
    - --target=$TARGET
    - $(is-enabled debug -g)

vcs:
  proxy: default
  options: none
  protocol: git
  url: ${TESTREPOS}/tlv

build: printf '%s\\n' build $GOPTS > $SCBI_BDIR/tlv-build.args

pre-install: printf '%s\\n' pre-install --prefix=$PREFIX $GOPTS > $SCBI_BDIR/tlv-pre-install.args

install: |-
  GOPTS += -p -f --prefix=$PREFIX
  printf '%s\\n' install $GOPTS > $SCBI_BDIR/tlv-install.args

wrapup: printf '%s\\n' wrapup $GOPTS > $SCBI_BDIR/tlv-wrapup.args
END
""")

    t.runs("./scbi tlv")

    t.runs("cat .root/builds/tlv-build.args .root/builds/tlv-pre-install.args .root/builds/tlv-install.args .root/builds/tlv-wrapup.args")
    t.clean_diff("""\
build
-XBUILD=PROD
--target=x86_64-linux-gnu
pre-install
--prefix=<pwd>/.root/builds/tlv/x86_64-linux-gnu-default/install
-XBUILD=PROD
--target=x86_64-linux-gnu
install
-XBUILD=PROD
--target=x86_64-linux-gnu
-p
-f
--prefix=<pwd>/.root/builds/tlv/x86_64-linux-gnu-default/install
wrapup
-XBUILD=PROD
--target=x86_64-linux-gnu
""")

    # an item depending on a feature
    t.runs("./scbi -f --enable-debug tlv")
    t.runs("cat .root/builds/tlv-build.args")
    t.diff("""\
build
-XBUILD=PROD
--target=x86_64-linux-gnu
-g
""")
