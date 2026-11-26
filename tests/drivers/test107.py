import pytest


@pytest.mark.requires("svn")
def test(t):
    #
    #  Add test for Subversion repository with standard and non standard layout.
    #
    #  repostd                      repomlt
    #     trunk                        trunk
    #        main.c                       prj1
    #        id.lst                          main.c
    #     branches                           id.lst
    #        main.c                       prj2
    #        id.lst                          main.c
    #     tags                               id.lst
    #        main.c                    branches
    #        id.lst                       prj1
    #                                        ...
    #                                     prj2
    #                                        ...
    #                                  tags
    #                                     prj1
    #                                        ...
    #                                     prj2
    #                                        ...
    #
    #  The layout <REPO>/prj1/[trunk/branches/tags] is not tested as it is
    #  the same as the standard layout. That is, the checkout url points to
    #  <REPO>/prj1 and we end up with root directory with trunk/branches/tags.
    #

    t.set('REP', '$PWD/.root/builds')

    t.sh('( cd $TESTREPOS && tar xf repostd.tar.bz2 && tar xf repomlt.tar.bz2 )')

    t.runs('./scbi --tests svnstd')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building svnstd [default] (trunk)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from subversion
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
prj trunk
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building svnstd [default] (trunk)
""")

    t.grep(*t.words('"svnstd subversion trunk revision r3" $REP/svnstd/source-ref'))

    t.runs('./scbi --tests svnstd:v1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building svnstd [default] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from subversion
xxxx/xx/xx xx:xx:xx : trigger: sources changed
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : tests starting
prj v1
xxxx/xx/xx xx:xx:xx : tests completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building svnstd [default] (v1)
""")

    t.runs('./scbi --tests svnmlt/prj1:v1.0')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building svnmlt [prj1] (v1.0)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from svn [prj1]
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build [prj1] starting
xxxx/xx/xx xx:xx:xx : build [prj1] completed
xxxx/xx/xx xx:xx:xx : install [prj1] starting
xxxx/xx/xx xx:xx:xx : install [prj1] completed
xxxx/xx/xx xx:xx:xx : tests [prj1] starting
prj prj1:v1.0
xxxx/xx/xx xx:xx:xx : tests [prj1] completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building svnmlt [prj1] (v1.0)
""")

    t.grep(*t.words('"svnmlt subversion v1.0 revision r10" $REP/svnmlt/source-ref'))

    t.runs('./scbi --tests svnmlt/prj2:v1')

    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building svnmlt [prj2] (v1)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install tests wrapup
xxxx/xx/xx xx:xx:xx : get sources from subversion [prj2]
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build [prj2] starting
xxxx/xx/xx xx:xx:xx : build [prj2] completed
xxxx/xx/xx xx:xx:xx : install [prj2] starting
xxxx/xx/xx xx:xx:xx : install [prj2] completed
xxxx/xx/xx xx:xx:xx : tests [prj2] starting
prj prj2:v1
xxxx/xx/xx xx:xx:xx : tests [prj2] completed
xxxx/xx/xx xx:xx:xx : skip global install
xxxx/xx/xx xx:xx:xx : End Building svnmlt [prj2] (v1)
""")

    t.grep(*t.words('"svnmlt subversion v1 revision r9" $REP/svnmlt/source-ref'))

    t.sh('cd $TESTREPOS && rm -fr repostd repomlt')
