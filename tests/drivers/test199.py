def test(t):
    #  A failed archive download never removes or overwrites the local
    #  archive and its SHA-1

    t.sh('rm -f .root/.archives/dltar-src.tar.bz2*')

    t.sh("""\
cp .root/.store/dltar-1-src.tar.bz2 .root/.store/dltar-src.tar.bz2
cp .root/.store/dltar-1-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1
""")

    t.runs('./scbi --tests --update dltar:#0')

    t.sh('sha1sum .root/.archives/dltar-src.tar.bz2 > .root/saved-archive.sha1')
    t.sh('cp .root/.archives/dltar-src.tar.bz2.sha1 .root/saved-local.sha1')

    #  The server returns an error page for the SHA-1, no archive

    t.sh("""\
rm -f .root/.store/dltar-src.tar.bz2
echo '<html><title>404 Not Found</title></html>' > .root/.store/dltar-src.tar.bz2.sha1
""")

    t.runs('./scbi --tests --update dltar:#0')
    t.runs('sha1sum .root/.archives/dltar-src.tar.bz2 | diff - .root/saved-archive.sha1')
    t.runs('diff .root/.archives/dltar-src.tar.bz2.sha1 .root/saved-local.sha1')

    #  A new SHA-1 on the server, its archive cannot be downloaded: the
    #  local one is used

    t.sh('cp .root/.store/dltar-2-src.tar.bz2.sha1 .root/.store/dltar-src.tar.bz2.sha1')

    t.runs('./scbi --tests --update dltar:#0')
    t.runs('sha1sum .root/.archives/dltar-src.tar.bz2 | diff - .root/saved-archive.sha1')
    t.runs('diff .root/.archives/dltar-src.tar.bz2.sha1 .root/saved-local.sha1')
    t.runs('grep "using local archive" .root/builds/.logs/x86_64-linux-gnu-dltar-report.log')

    #  Without update, the sources removed: the local archive (matching
    #  its SHA-1) is extracted, the server is not accessed

    t.sh('rm -f .root/.store/dltar-src.tar.bz2.sha1')
    t.sh('rm -rf $(find .root/builds -type d -name archive-src)')

    t.runs('./scbi --tests dltar:#0')
    t.grep('extract archive dltar-src.tar.bz2')
    t.runs('sha1sum .root/.archives/dltar-src.tar.bz2 | diff - .root/saved-archive.sha1')
    t.runs('diff .root/.archives/dltar-src.tar.bz2.sha1 .root/saved-local.sha1')
