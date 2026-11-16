def test(t):
    # Some tests for scbi source-archive

    #################### DEFAULT

    t.runs('./scbi source-archive libarch:v1')

    t.clean_diff("""\
Create source archive for libarch [default] (v1)
  from  <pwd>/.root/repos/lib1.bundle
    to  lib1-v1.tar.gz
""")

    t.runs('tar tf lib1-v1.tar.gz')

    t.sort_output()

    t.diff("""\
lib1.bundle/
lib1.bundle/Makefile
lib1.bundle/lib1.c
lib1.bundle/lib1.h
lib1.bundle/main.c
""")

    t.ok('! -f lib1-v1.tar.gz.sha1')
    t.ok('! -f lib1-v1.tar.gz.sha256')

    t.sh('rm lib1-v1.tar.gz')

    #################### GZ

    t.runs('./scbi source-archive libarch/gz')

    t.clean_diff("""\
Create source archive for libarch [gz] (master)
  from  <pwd>/.root/repos/lib1.bundle
    to  libarch-master-src.tar.gz
""")

    t.runs('tar tf libarch-master-src.tar.gz')

    t.sort_output()

    t.diff("""\
lib1.bundle/
lib1.bundle/Makefile
lib1.bundle/lib1.c
lib1.bundle/lib1.h
lib1.bundle/main.c
""")

    t.sh('rm libarch-master-src.tar.gz')

    #################### BZ2

    t.runs('./scbi source-archive libarch/bz2:v2')

    t.clean_diff("""\
Create source archive for libarch [bz2] (v2)
  from  <pwd>/.root/repos/lib1.bundle
    to  libarch-v2.tar.bz2
""")

    t.runs('tar tf libarch-v2.tar.bz2')

    t.sort_output()

    t.diff("""\
lib1.bundle/
lib1.bundle/Makefile
lib1.bundle/lib1.c
lib1.bundle/lib1.h
lib1.bundle/main.c
""")

    t.sh('rm libarch-v2.tar.bz2')

    #################### TAR

    t.runs('./scbi source-archive --lower-case libarch/tar:v1')

    t.clean_diff("""\
Create source archive for libarch [tar] (v1)
  from  <pwd>/.root/repos/lib1.bundle
    to  libarch-v1-nocomp.tar
""")

    t.runs('tar tf libarch-v1-nocomp.tar')

    t.sort_output()

    t.diff("""\
lib1.bundle/
lib1.bundle/Makefile
lib1.bundle/lib1.c
lib1.bundle/lib1.h
lib1.bundle/main.c
""")

    t.sh('rm libarch-v1-nocomp.tar')

    #################### XZ

    t.runs('./scbi source-archive --sha1 libarch/xz')

    t.clean_diff("""\
Create source archive for libarch [xz] (master)
  from  <pwd>/.root/repos/lib1.bundle
    to  libarch-master.tar.xz
""")

    t.runs('tar tf libarch-master.tar.xz')

    t.sort_output()

    t.diff("""\
lib1.bundle/
lib1.bundle/Makefile
lib1.bundle/lib1.c
lib1.bundle/lib1.h
lib1.bundle/main.c
""")

    t.ok('-f libarch-master.tar.xz.sha1')

    t.sh('rm libarch-master.tar.xz*')

    #################### ZIP

    t.runs('./scbi source-archive --sha256 --clean-version libarch/zip:v1')

    t.clean_diff("""\
Create source archive for libarch [zip] (v1)
  from  <pwd>/.root/repos/lib1.bundle
    to  libarch-1.zip
""")

    t.runs('zipinfo -1 libarch-1.zip')

    t.sort_output()

    t.diff("""\
lib1.bundle/
lib1.bundle/Makefile
lib1.bundle/lib1.c
lib1.bundle/lib1.h
lib1.bundle/main.c
""")

    t.ok('-f libarch-1.zip.sha256')

    t.sh('rm libarch-1.zip*')
