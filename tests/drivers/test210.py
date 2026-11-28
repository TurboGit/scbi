def test(t):
    # archive-sha256: the SHA-256 of the archives given by the plug-in

    t.set('A', '.root/.archives')
    t.set('SUM', '83d171134b09bf6df5b6ba0527fc7b02740d2c258110a5076b083eb4aa454ee6')
    t.set('BAD', '0000000000000000000000000000000000000000000000000000000000000000')

    # no hash: as before
    t.runs('./scbi --no-patch lib1:#v1.2')
    t.grep('End Building lib1')

    # the line to paste
    t.runs('./scbi show --archive-sha256 lib1:#v1.2')
    t.clean_diff("""\
# lib1
83d171134b09bf6df5b6ba0527fc7b02740d2c258110a5076b083eb4aa454ee6  lib1-v1.2-src.tar.bz2
""")

    # the right SHA-256 (sha256sum format, binary marker): not part of the
    # build id, nothing to rebuild
    t.sh('printf "archive-sha256:\\n  - $SUM *lib1-v1.2-src.tar.bz2\\n" >> scripts.d/lib1.yaml')
    t.runs('./scbi --no-patch lib1:#v1.2')
    t.grep('no build needed')
    t.ngrep('mismatch')

    # a wrong one: not extracted, the build fails; a local archive is kept
    t.sh('sed -i "s/$SUM/$BAD/" scripts.d/lib1.yaml')
    t.nruns('./scbi --no-patch --force lib1:#v1.2')
    t.grep('archive lib1-v1.2-src.tar.bz2 SHA-256 mismatch (expected 0000000000000000000000000000000000000000000000000000000000000000, got 83d171134b09bf6df5b6ba0527fc7b02740d2c258110a5076b083eb4aa454ee6)')
    t.ngrep('End Building lib1')
    t.ok('-f $A/lib1-v1.2-src.tar.bz2')
    t.nok('-d .root/builds/lib1/archive-src')

    # a SHA-256 for another file only: not checked
    t.sh('sed -i "s/$BAD \\*lib1-v1.2-src.tar.bz2/$BAD lib1-v9-src.tar.bz2/" scripts.d/lib1.yaml')
    t.runs('./scbi --no-patch --force lib1:#v1.2')
    t.grep('End Building lib1')

    # a downloaded archive with a wrong SHA-256: renamed .bad, downloaded
    # again at the next run
    t.sh('rm -f $A/dltar-src.tar.bz2*')
    t.sh('cp .root/.store/dltar-1-src.tar.bz2 .root/.store/dltar-src.tar.bz2;'
         ' cp .root/.store/dltar-1-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1')
    t.sh('printf "archive-sha256:\\n  - $BAD  dltar-src.tar.bz2\\n" >> scripts.d/dltar.yaml')
    t.nruns('./scbi --update dltar:#0')
    t.grep('archive dltar-src.tar.bz2 SHA-256 mismatch')
    t.ok('-f $A/dltar-src.tar.bz2.bad')
    t.nok('-f $A/dltar-src.tar.bz2')
    t.sh('sed -i "s/$BAD/$(sha256sum < .root/.store/dltar-src.tar.bz2 | cut -d\\" \\" -f1)/" scripts.d/dltar.yaml')
    t.runs('./scbi --update dltar:#0')
    t.grep('End Building dltar')
    t.ok('-f $A/dltar-src.tar.bz2')

    # the SBOM gives the SHA-256 of the archive
    t.runs('./scbi show --sbom lib1:#v1.2')
    t.grep('"alg": "SHA-256"')

    # scbi lint: the lines of the hook
    t.sh('''cat > shabad.yaml <<XEOF
plugin: shabad
archive-sha256:
  - not-a-sum  x.tar.gz
  - $SUM  a.tar.gz
  - $BAD  a.tar.gz
XEOF
cat > shaok.yaml <<XEOF
plugin: shaok
archive:
  _:
    proxy: default
    options: none
    protocol: curl
    url: https://example.org
    file: a-\\$VERSION.tar.gz
  zip:
    proxy: default
    options: none
    protocol: curl
    url: https://example.org
    file: a-zip-\\${VERSION}.zip
archive-sha256:
  - $SUM  a-1.tar.gz
  - $BAD *a-2.tar.gz
  - $BAD  a-zip-3.zip
XEOF
cat > shaname.yaml <<XEOF
plugin: shaname
archive:
  proxy: default
  options: none
  protocol: curl
  url: https://example.org
  file: a-\\$VERSION.tar.gz
archive-sha256:
  - $SUM  b-1.tar.gz
XEOF''')
    t.nruns('./scbi lint shabad.yaml')
    t.clean_diff("""\

========== Handle shabad.yaml
   error:   (archive-sha256) 'not-a-sum  x.tar.gz' is not '<sha256>  <file>' (as printed by sha256sum)
   error:   (archive-sha256) two different SHA-256 for a.tar.gz
   warning: (archive-sha256) no archive hook
""")
    t.runs('./scbi lint shaok.yaml')
    t.clean_diff("""\

========== Handle shaok.yaml
""")
    # the file names: the ones of the archive hook
    t.nruns('./scbi lint shaname.yaml')
    t.clean_diff("""\

========== Handle shaname.yaml
   error:   (archive-sha256) b-1.tar.gz is not an archive of the archive hook (a-$VERSION.tar.gz)
""")
