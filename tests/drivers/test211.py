def test(t):
    # the binary store: a build of a sandbox installed in another one, its
    # paths relocated

    t.set('BS', '$ROOTDIR/.root/.binaries')
    t.set('SCBI_BINARY_STORE', 'file://$BS')
    t.set('A', '$ROOTDIR/.root/builds')
    t.set('B', '$ROOTDIR/.root/b')
    t.set('C', '$ROOTDIR/.root/builds-a-much-longer-sandbox-path')
    t.set('TV', 'x86_64-linux-gnu-default/install')

    t.sh('''cat > scripts.d/mkbin.sh <<'XEOF'
# a binary file holding a path in a C string (raw: not NUL-terminated)
if [ "$2" = raw ]; then
  printf '\\177ELF\\000\\000%s' "$1" > "$1/lib/librelo.bin"
else
  printf '\\177ELF\\000\\000%s/lib\\000tail\\000' "$1" > "$1/lib/librelo.bin"
fi
XEOF
cat > scripts.d/relodep.yaml <<'XEOF'
plugin: relodep

env:
  - set-var RELODEP_DIR $PREFIX

install: |-
  mkdir -p $PREFIX/lib/pkgconfig
  write $PREFIX/lib/pkgconfig/relodep.pc:
      prefix=$PREFIX
XEOF
cat > scripts.d/relo.yaml <<'XEOF'
plugin: relo

depends:
  - relodep

install:
  _: |-
    mkdir -p $PREFIX/bin
    mkdir -p $PREFIX/lib
    write $PREFIX/bin/relo-config:
        #!/bin/sh
        echo $PREFIX $RELODEP_DIR
    sh $SCBI_PLUGINS/mkbin.sh $PREFIX
    ln -s $PREFIX/lib/librelo.bin $PREFIX/lib/librelo.so
  raw: |-
    mkdir -p $PREFIX/lib
    sh $SCBI_PLUGINS/mkbin.sh $PREFIX raw
XEOF''')

    # sandbox A: built, written to the store
    t.runs('./scbi -d relo')
    t.ngrep('from binary store')
    t.runs('ls $BS/x86_64-linux-gnu/relo $BS/x86_64-linux-gnu/relodep | grep -c json')
    t.clean_diff("""\
2
""")

    # sandbox B: installed from the store, relocated
    t.runs('./scbi -d --build-dir=$B relo')
    t.sh('cp $TEST_OUTPUT b.out')
    for m in ('relodep', 'relo'):
        t.runs(f'sed -n "/Building {m} /,/End Building {m} /p" b.out')
        t.grep('trigger: from binary store file://')
        t.grep('install cached')
    t.runs('cat $B/relo/$TV/bin/relo-config')
    t.grep('/.root/b/relo/')
    t.grep('/.root/b/relodep/')
    t.ngrep('/.root/builds/')
    t.runs('cat $B/relodep/$TV/lib/pkgconfig/relodep.pc')
    t.grep('prefix=.*/.root/b/relodep/')
    t.runs('grep -a -c "/.root/b/relo/$TV/lib" $B/relo/$TV/lib/librelo.bin')
    t.runs('grep -a -c "/.root/builds/" $B/relo/$TV/lib/librelo.bin || true')
    t.clean_diff("""\
0
""")
    t.runs('readlink $B/relo/$TV/lib/librelo.so')
    t.grep('/.root/b/relo/')
    # up to date afterwards
    t.runs('./scbi -d --build-dir=$B relo')
    t.sh('grep -c "no build needed" $TEST_OUTPUT > x; mv x $TEST_OUTPUT')
    t.clean_diff("""\
2
""")

    # the keys
    t.runs('./scbi binary-store --show-key --build-dir=$B relo')
    t.grep('relocatable .* file://')

    # sandbox C, a longer path: the binary file cannot be relocated, relo
    # is built; relodep (text) is installed
    t.runs('./scbi -d --build-dir=$C relo')
    t.sh('cp $TEST_OUTPUT c.out')
    t.runs('sed -n "/Building relodep /,/End Building relodep /p" c.out')
    t.grep('trigger: from binary store')
    t.runs('sed -n "/Building relo /,/End Building relo /p" c.out')
    t.grep('warning: binary store .*longer than the origin one (in a binary file), building')
    t.grep('install completed')

    # not relocatable (a path not in a C string): stored bound to its
    # sandbox, reused there only
    t.runs('./scbi -d relo/raw')
    t.runs('python3 -c "import json,glob; print(sorted(json.load(open(f))[\\"kind\\"] for f in glob.glob(\\"$BS/x86_64-linux-gnu/relo/*.json\\")))"')
    t.grep("'bound'")
    t.runs('./scbi -d --build-dir=$B relo/raw')
    t.ngrep('trigger: from binary store')
    t.runs('./scbi -d --purge relo/raw')
    t.grep('trigger: from binary store')

    # another environment (a variable of the environment file): no match
    t.sh('printf "vars:\\n  OPT_FLAGS: -O3\\n" > scripts.d/.env-bs.yaml')
    t.runs('./scbi -d -e bs --build-dir=$ROOTDIR/.root/d relo')
    t.ngrep('from binary store')

    # a corrupted entry: a warning, built
    t.sh('for f in $BS/x86_64-linux-gnu/relodep/*.tar.*; do printf x >> $f; done')
    t.runs('./scbi -d --build-dir=$ROOTDIR/.root/e relodep')
    t.grep('warning: binary store .*corrupted (SHA-256), building')
    t.grep('relodep')
