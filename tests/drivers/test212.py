def test(t):
    # the binary stores: several stores, read-only ones, the options of a
    # run, the transports of the environment file, a Web server,
    # scbi binary-store --list and --explain

    t.set('S', '$ROOTDIR/.root/stores')
    t.set('TV', 'x86_64-linux-gnu-default')
    t.sh('''cat > scripts.d/bsmod.yaml <<'XEOF'
plugin: bsmod

install: |-
  mkdir -p $PREFIX/lib/pkgconfig
  write $PREFIX/lib/pkgconfig/bsmod.pc:
      prefix=$PREFIX
      flags=$OPT_FLAGS
XEOF''')

    def count(store):
        return f'ls {store}/x86_64-linux-gnu/bsmod 2>/dev/null | grep -c json || true'

    # the team store only
    t.set('SCBI_BINARY_STORE', 'file://$S/team')
    t.runs('./scbi --build-dir=$ROOTDIR/.root/a bsmod')
    t.runs(count('$S/team'))
    t.clean_diff("""\
1
""")

    # a local store first: the hit in the team store is copied into it
    t.sh('export SCBI_BINARY_STORE="file://$S/local file://$S/team"')
    t.runs('./scbi --build-dir=$ROOTDIR/.root/b bsmod')
    t.grep('trigger: from binary store file://.*/team')
    t.runs(count('$S/local'))
    t.clean_diff("""\
1
""")

    # a read-only store, --binary-store:pull: not written
    t.sh('printf "vars:\\n  OPT_FLAGS: -O1\\n" > scripts.d/.env-o1.yaml')
    t.sh('export SCBI_BINARY_STORE="file://$S/local ro:file://$S/ro"')
    t.runs('./scbi -e o1 --build-dir=$ROOTDIR/.root/c bsmod')
    t.runs(count('$S/ro'))
    t.clean_diff("""\
0
""")
    t.runs(count('$S/local'))
    t.clean_diff("""\
2
""")
    t.set('SCBI_BINARY_STORE', 'file://$S/pull')
    t.runs('./scbi --binary-store:pull --build-dir=$ROOTDIR/.root/d bsmod')
    t.runs(count('$S/pull'))
    t.clean_diff("""\
0
""")

    # --binary-store=<url>: a store first for the run; :no: none
    t.runs('./scbi --binary-store=file://$S/extra --build-dir=$ROOTDIR/.root/e bsmod')
    t.runs(count('$S/extra'))
    t.clean_diff("""\
1
""")
    t.runs('./scbi --binary-store:no --binary-store=file://$S/extra --build-dir=$ROOTDIR/.root/f bsmod')
    t.ngrep('from binary store')

    # the stores and the transport of the environment file
    t.unset('SCBI_BINARY_STORE')
    t.sh('''cat > scripts.d/.env-cp.yaml <<'XEOF'
binary-stores:
  - cp://$SCBI_ROOT/stores/cp
functions:
  binary-store-get:
    params: [URL, PATH, DEST]
    run: |-
      SRC = ${URL#cp://}/$PATH
      if is-file($SRC):
          cp $SRC $DEST
      else:
          return 1
  binary-store-put:
    params: [URL, FILE, PATH]
    run: |-
      DST = ${URL#cp://}/$PATH
      mkdir -p $(dirname $DST)
      cp $FILE $DST
  binary-store-list:
    params: [URL, DIR]
    run: ls ${URL#cp://}/$DIR
XEOF''')
    t.runs('./scbi -e cp --build-dir=$ROOTDIR/.root/g bsmod')
    t.runs(count('$S/cp'))
    t.clean_diff("""\
1
""")
    t.runs('./scbi -e cp --build-dir=$ROOTDIR/.root/h bsmod')
    t.grep('trigger: from binary store cp://')
    t.runs('./scbi binary-store -e cp --list bsmod')
    t.grep('^cp://.* (rw):')
    t.grep('bsmod .* relocatable')

    # binary-key: a value added to the keys
    t.sh('''cat scripts.d/.env-cp.yaml > scripts.d/.env-cpk.yaml
cat >> scripts.d/.env-cpk.yaml <<'XEOF'
  binary-key:
    params: [MODULE, VARIANT, TARGET]
    run: echo toolchain-2
XEOF''')
    t.runs('./scbi -e cpk --build-dir=$ROOTDIR/.root/i bsmod')
    t.ngrep('from binary store')

    # --explain: what differs (the value of binary-key)
    t.runs('./scbi binary-store -e cp --build-dir=$ROOTDIR/.root/i --explain bsmod')
    t.grep("extra: 'toolchain-2' here, '' in the entry")

    # a Web server (GET): python3 -m http.server on the team store
    t.sh('PORT=$(python3 -c "import socket; s=socket.socket(); s.bind((\\"127.0.0.1\\", 0)); print(s.getsockname()[1])");'
         ' (cd $S/team && exec timeout 120 python3 -m http.server --bind 127.0.0.1 $PORT > /dev/null 2>&1) & echo $! > http.pid;'
         ' echo $PORT > http.port; for i in $(seq 50); do curl -s -o /dev/null http://127.0.0.1:$PORT/ && break; sleep 0.1; done')
    t.sh('export SCBI_BINARY_STORE=ro:http://127.0.0.1:$(cat http.port)')
    t.runs('./scbi --build-dir=$ROOTDIR/.root/j bsmod')
    t.grep('trigger: from binary store http://127.0.0.1:')
    t.runs('./scbi binary-store --list bsmod')
    t.grep('bsmod .* relocatable')
    t.sh('kill $(cat http.pid)')
