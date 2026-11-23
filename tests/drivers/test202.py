def test(t):
    # The base environment of a module from a sandbox plug-in, first item
    # of its build-depends, with variants defined only by qualifiers:
    #   sbx         native sandbox, or the target environment in cross
    #   sbx/host    native sandbox, also in cross (tools running on the host)
    #   sbx/system  the system tools only
    # The driver adds no compiler environment of its own in cross builds.

    t.sh("""\
mkdir -p sbx/bin sbx/x86_64-w64-mingw32/bin xdep/bin
cat > scripts.d/sbx.yaml <<EOF
plugin: sbx

env:
  _:
    - add-to-var PATH $PWD/sbx/bin
  host:
    - add-to-var PATH $PWD/sbx/bin
  system:
    - export PATH /usr/local/bin:/usr/bin:/bin
    - unset-var C_INCLUDE_PATH
  cross:
    _:
      - add-to-var PATH $PWD/sbx/bin
      - unset-var C_INCLUDE_PATH
      - set-var PKG_CONFIG_LIBDIR $PWD/sbx/\\$TARGET/lib/pkgconfig
EOF
cat > scripts.d/xdep.yaml <<EOF
plugin: xdep

env:
  - add-to-var PATH $PWD/xdep/bin
EOF
for m in xlib xtool xsys; do
  case $m in
    xlib) bd="  - sbx";;
    xtool) bd="  - sbx/host";;
    xsys) bd="  - sbx/system
  - xdep";;
  esac
  cat > scripts.d/$m.yaml <<EOF
plugin: $m

build-depends:
$bd

build: |-
  echo "$m PATH=\\$PATH" > \\$SCBI_BDIR/$m.env
  echo "$m C_INCLUDE_PATH=\\${C_INCLUDE_PATH:-unset}" >> \\$SCBI_BDIR/$m.env
  echo "$m PKG_CONFIG_LIBDIR=\\${PKG_CONFIG_LIBDIR:-unset}" >> \\$SCBI_BDIR/$m.env
EOF
done
""")

    t.set('C_INCLUDE_PATH', '/host/include')
    t.unset('PKG_CONFIG_LIBDIR')

    def check(target):
        t.runs(f'./scbi --deps -I -W {target} xlib xtool xsys')
        #  the PATH of the test shown as <path>
        t.runs('cat .root/builds/xlib.env .root/builds/xtool.env .root/builds/xsys.env'
               ' | sed -e "s|$PATH|<path>|"')

    # =================== native: the sandbox for all but xsys
    check('')
    t.clean_diff("""\
xlib PATH=<pwd>/sbx/bin:<path>
xlib C_INCLUDE_PATH=/host/include
xlib PKG_CONFIG_LIBDIR=unset
xtool PATH=<pwd>/sbx/bin:<path>
xtool C_INCLUDE_PATH=/host/include
xtool PKG_CONFIG_LIBDIR=unset
xsys PATH=<pwd>/xdep/bin:/usr/local/bin:/usr/bin:/bin
xsys C_INCLUDE_PATH=unset
xsys PKG_CONFIG_LIBDIR=unset
""")

    # =================== cross: the target environment for xlib only
    check('--target=x86_64-w64-mingw32')
    t.clean_diff("""\
xlib PATH=<pwd>/sbx/bin:<path>
xlib C_INCLUDE_PATH=unset
xlib PKG_CONFIG_LIBDIR=<pwd>/sbx/x86_64-w64-mingw32/lib/pkgconfig
xtool PATH=<pwd>/sbx/bin:<path>
xtool C_INCLUDE_PATH=/host/include
xtool PKG_CONFIG_LIBDIR=unset
xsys PATH=<pwd>/xdep/bin:/usr/local/bin:/usr/bin:/bin
xsys C_INCLUDE_PATH=unset
xsys PKG_CONFIG_LIBDIR=unset
""")
