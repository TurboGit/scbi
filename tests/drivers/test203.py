def test(t):
    # host@<module>: a dependency built for the host, whatever the target.
    # In a cross build it is built by a run of the driver for the host
    # (--deps), its environment and build id are the ones of that build.

    t.sh("""\
cat > scripts.d/htool.yaml <<'EOF'
plugin: htool

env:
  - add-to-var PATH $PREFIX/bin

build: echo $TARGET > htool-target

install: |-
  mkdir -p $PREFIX/bin
  copy htool-target $PREFIX/bin
EOF
cat > scripts.d/hlib.yaml <<'EOF'
plugin: hlib

build-depends:
  - host@htool

build: |-
  D = module-dir htool
  echo "htool for $(output cat $D/bin/htool-target)" > $SCBI_BDIR/hlib-$TARGET.txt
  echo "PATH ${PATH%%:*}" >> $SCBI_BDIR/hlib-$TARGET.txt
EOF
""")

    # =================== native: host@htool is htool
    t.runs('./scbi --deps -W hlib')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building htool [default] (n/a)
xxxx/xx/xx xx:xx:xx : needed by:
xxxx/xx/xx xx:xx:xx :   ↳ hlib
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : install starting
xxxx/xx/xx xx:xx:xx : install completed
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building htool [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building hlib [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building hlib [default] (n/a)
""")
    t.runs('cat .root/builds/hlib-x86_64-linux-gnu.txt')
    t.clean_diff("""\
htool for x86_64-linux-gnu
PATH <pwd>/.root/builds/htool/x86_64-linux-gnu-default/install/bin
""")

    # =================== cross: htool built for the host only
    t.runs('./scbi --deps -W --target=x86_64-w64-mingw32 hlib')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building htool for the host x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : Building htool [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building htool [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building hlib [default] (n/a)
xxxx/xx/xx xx:xx:xx : cross x86_64-w64-mingw32
xxxx/xx/xx xx:xx:xx : steps: setup config build install
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: not yet built
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building hlib [default] (n/a)
""")
    t.runs('cat .root/builds/hlib-x86_64-w64-mingw32.txt; ls .root/builds/htool')
    t.clean_diff("""\
htool for x86_64-linux-gnu
PATH <pwd>/.root/builds/htool/x86_64-linux-gnu-default/install/bin
build
build-id-default
install-x86_64-linux-gnu-id
source-id
source-id-default
source-ref
x86_64-linux-gnu-default
""")

    # =================== cross again: nothing rebuilt
    t.runs('./scbi --deps -W --target=x86_64-w64-mingw32 hlib')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building htool for the host x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : Building htool [default] (n/a)
xxxx/xx/xx xx:xx:xx : native x86_64-linux-gnu
xxxx/xx/xx xx:xx:xx : steps: setup config build install wrapup
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : copy install into <sandbox>/install
xxxx/xx/xx xx:xx:xx : End Building htool [default] (n/a)

xxxx/xx/xx xx:xx:xx : Building hlib [default] (n/a)
xxxx/xx/xx xx:xx:xx : cross x86_64-w64-mingw32
xxxx/xx/xx xx:xx:xx : steps: setup config build install
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : no build needed: versions matching
xxxx/xx/xx xx:xx:xx : End Building hlib [default] (n/a)
""")

    # =================== a new build of htool for the host rebuilds hlib
    t.sh("sed -i 's/^build: echo/build: echo -n/' scripts.d/htool.yaml")
    t.runs('./scbi -W htool')
    t.runs('./scbi -W --target=x86_64-w64-mingw32 hlib')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : Building hlib [default] (n/a)
xxxx/xx/xx xx:xx:xx : cross x86_64-w64-mingw32
xxxx/xx/xx xx:xx:xx : steps: setup config build install
xxxx/xx/xx xx:xx:xx : no sources (vcs or tar)
xxxx/xx/xx xx:xx:xx : trigger: build not up-to-date
xxxx/xx/xx xx:xx:xx : build starting
xxxx/xx/xx xx:xx:xx : build completed
xxxx/xx/xx xx:xx:xx : End Building hlib [default] (n/a)
""")

    # =================== without --deps: the build for the host must exist
    t.runs('rm -rf .root/builds/htool/x86_64-linux-gnu-default')
    t.nruns('./scbi -W --target=x86_64-w64-mingw32 hlib')
    t.clean_diff("""\
xxxx/xx/xx xx:xx:xx : hlib (FAILED) host@htool: not built for x86_64-linux-gnu, run scbi htool or use --deps
""")

    # =================== with --deps: built for the host by a run of the driver
    t.runs('./scbi --deps -W --target=x86_64-w64-mingw32 hlib')
    t.grep('Building htool for the host')
    t.runs('cat .root/builds/htool/x86_64-linux-gnu-default/install/bin/htool-target')
    t.clean_diff("""\
x86_64-linux-gnu
""")

    # =================== htool can still be built for the target
    t.runs('./scbi -W --target=x86_64-w64-mingw32 htool')
    t.runs('cat .root/builds/htool/x86_64-w64-mingw32-default/install/bin/htool-target')
    t.clean_diff("""\
x86_64-w64-mingw32
""")

    # =================== show: the dependency for the host
    t.runs('./scbi show --depends:full hlib')
    t.clean_diff("""\
hlib
htool
""")
    t.runs('./scbi --target=x86_64-w64-mingw32 show --depends:full hlib')
    t.clean_diff("""\
hlib
host@htool
""")

    # =================== host@ an aggregate meta-module: the environment of
    # its modules built for the host
    t.sh("""\
cat > scripts.d/hkit.yaml <<'EOF2'
plugin: hkit

modules:
  - htool

aggregate: direct
EOF2
cat > scripts.d/hlib2.yaml <<'EOF2'
plugin: hlib2

build-depends:
  - host@hkit

build: echo "PATH ${PATH%%:*}" > $SCBI_BDIR/hlib2-$TARGET.txt
EOF2
""")
    t.runs('./scbi --deps -W --target=x86_64-w64-mingw32 hlib2')
    t.runs('cat .root/builds/hlib2-x86_64-w64-mingw32.txt')
    t.clean_diff("""\
PATH <pwd>/.root/builds/hkit/x86_64-linux-gnu-default/install/bin
""")
