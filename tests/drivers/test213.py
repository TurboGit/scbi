def test(t):
    # the binary stores: --gc, --rm, SCBI_BINARY_STORE_MAX_SIZE, the
    # signature of the entries

    t.set('S', '$ROOTDIR/.root/store')
    t.set('SCBI_BINARY_STORE', 'file://$S')
    t.set('E', '$S/x86_64-linux-gnu')
    # three modules installing 300 KB of incompressible data
    t.sh('''for m in gm1 gm2 gm3; do
cat > scripts.d/$m.yaml <<XEOF
plugin: $m

install: |-
  mkdir -p \\$PREFIX/lib
  head -c 300000 /dev/urandom > \\$PREFIX/lib/$m.data
XEOF
done''')
    t.runs('./scbi gm1 gm2 gm3')
    t.runs('ls $E | wc -l')
    t.clean_diff("""\
3
""")

    # gm1 not used for 10 days, gm2 for 2 days
    t.sh('touch -d "10 days ago" $E/gm1/*.json; touch -d "2 days ago" $E/gm2/*.json')

    # by age: --dry-run lists, removes nothing
    t.runs('./scbi binary-store --gc --older-than=5 --dry-run')
    t.grep('1 entry to remove')
    t.grep('  gm1 ')
    t.runs('ls $E/gm1 | wc -l')
    t.clean_diff("""\
2
""")
    t.runs('./scbi binary-store --gc --older-than=5d')
    t.grep('1 entry removed')
    t.runs('ls $E/gm1 | wc -l')
    t.clean_diff("""\
0
""")

    # by size: the least recently used first (gm2)
    t.runs('./scbi binary-store --gc --max-size=400K')
    t.grep('  gm2 ')
    t.runs('ls $E/gm2 $E/gm3 | grep -c json')
    t.clean_diff("""\
1
""")
    t.runs('ls $E/gm3 | grep -c json')

    # --rm: a key prefix
    t.runs('ls $E/gm3/*.json | sed "s|.*/||" | cut -c1-12')
    t.sh('cp $TEST_OUTPUT key3')
    t.runs('./scbi binary-store --rm $(cat key3)')
    t.grep('removed gm3')
    t.runs('ls $E/gm3 | wc -l')
    t.clean_diff("""\
0
""")
    t.nruns('./scbi binary-store --rm abc')
    t.grep('keys (8 characters at least) expected')

    # SCBI_BINARY_STORE_MAX_SIZE: the store reduced at the end of a build
    t.set('SCBI_BINARY_STORE_MAX_SIZE', '700K')
    t.runs('./scbi --force gm1 gm2 gm3')
    t.runs('ls $E/*/*.json | wc -l')
    t.clean_diff("""\
2
""")
    t.unset('SCBI_BINARY_STORE_MAX_SIZE')

    # the signature of the metadata (environment file)
    t.sh('''cat > scripts.d/.env-sig.yaml <<'XEOF'
functions:
  binary-store-sign:
    params: [FILE, SIG]
    run: sh -c 'sha256sum "$0" | cut -c1-64 > "$1"' $FILE $SIG
  binary-store-verify:
    params: [FILE, SIG]
    run: sh -c 'test "$(sha256sum "$0" | cut -c1-64)" = "$(cat "$1")"' $FILE $SIG
XEOF''')
    t.set('SCBI_BINARY_STORE', 'file://$ROOTDIR/.root/signed')
    t.runs('./scbi -e sig --build-dir=$ROOTDIR/.root/a gm1')
    t.runs('ls $ROOTDIR/.root/signed/x86_64-linux-gnu/gm1 | grep -c "json.sig$"')
    t.clean_diff("""\
1
""")
    t.runs('./scbi -e sig --build-dir=$ROOTDIR/.root/b gm1')
    t.grep('trigger: from binary store')
    # a signature not valid: not used
    t.sh('for f in $ROOTDIR/.root/signed/x86_64-linux-gnu/gm1/*.sig; do echo bad > $f; done')
    t.runs('./scbi -e sig --build-dir=$ROOTDIR/.root/c gm1')
    t.grep('signature not valid')
    t.ngrep('trigger: from binary store')
    # an entry not signed (the first store): not used when verified
    t.set('SCBI_BINARY_STORE', 'file://$S')
    t.runs('./scbi -e sig --build-dir=$ROOTDIR/.root/d gm2')
    t.grep('not signed')
    t.ngrep('trigger: from binary store')
