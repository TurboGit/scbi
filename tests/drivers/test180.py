def test(t):
    # scbi show --resolved: the plug-in of a module resolved for its
    # module reference (variants, common, cross, inheritance, OS variants,
    # guards)

    # =================== default variant: the plain hooks, inherited ones
    t.runs('./scbi show --resolved resapp')

    t.diff("""\
#  Plug-in resapp resolved for resapp/default (scbi show --resolved)
#  target x86_64-linux-gnu, plan (none)

plugin: resapp

vars:
  BASEV: base
  APPV: app

functions:
  helper:
    params:
      - X
    run: echo helper $X

depends:
  - lib1
  - dep1

env:
  - set-var RESAPP_ROOT $PREFIX
  - set-var RESAPP_CROSS no
  - add-to-var PATH $PREFIX/bin

config-options:
  - --prefix=$PREFIX
  - --plain

config: ../src/configure $(config-options)

build: make

install: make install
""")

    # =================== a variant including others, guards evaluated
    t.runs('./scbi --enable-feat show --resolved resapp/all')

    t.diff("""\
#  Plug-in resapp resolved for resapp/all (scbi show --resolved)
#  target x86_64-linux-gnu, plan (none)

plugin: resapp

vars:
  BASEV: base
  APPV: app

functions:
  helper:
    params:
      - X
    run: echo helper $X

depends:
  - lib1
  - gtk
  - curl

env:
  - set-var RESAPP_ROOT $PREFIX
  - set-var RESAPP_CROSS no
  - set-var RESAPP_FEAT on

config-options:
  - --prefix=$PREFIX
  - --with-gui
  - --with-net

config: |-
  ../src/configure --gui $(config-options)
  if cross:
      echo cross

build: make

install: make install
""")

    # =================== cross target, version given
    t.runs('./scbi --target=x86_64-w64-mingw32 show --resolved resapp/net:1.2')
    t.grep(r'^#  Plug-in resapp resolved for resapp/net:1.2 (scbi show --resolved)$')
    t.grep(r'^#  target x86_64-w64-mingw32 (cross), plan (none)$')
    t.grep('^  - winsock$')
    t.grep('^  - set-var RESAPP_CROSS yes$')
    t.grep(r'^config: ../src/configure --cross \$(config-options)$')
    t.ngrep('host=')

    # =================== OS variant: no placeholder hooks
    t.runs('./scbi show --resolved resapp/native')
    t.grep('^  - os@-resapp$')
    t.grep('^  - set-var RESAPP_NATIVE yes$')
    t.grep('^config: true$')
    t.ngrep('pre-config')
    t.ngrep('patches')

    # =================== the result is a valid plug-in
    t.sh('mkdir -p res; ./scbi show --resolved resapp/gui > res/resapp.yaml')
    t.runs('./scbi lint --error res/resapp.yaml')

    # =================== unknown plug-in
    t.nruns('./scbi show --resolved nosuchplugin')
