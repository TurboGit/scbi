import pytest


@pytest.mark.requires("strace")
def test(t):
    # --check-deps:trace: the files opened and the programs run by the
    # commands of the steps, recorded with strace

    t.sh('''cat > scripts.d/trc.yaml <<'XEOF'
plugin: trc

depends:
  ok:
    - lib1
  tool:
    - lib1

build:
  _: |-
    cat $SCBI_PREFIX/include/lib1.h > copy.h
  ok: |-
    cat $SCBI_PREFIX/include/lib1.h > copy.h
  tool: |-
    $SCBI_PREFIX/bin/main > /dev/null || true
XEOF''')
    t.runs('./scbi lib1')

    # without trace: no dependency file, nothing seen
    t.runs('./scbi --check-deps trc')
    t.ngrep('not a dependency')

    # with trace: the header read
    t.runs('./scbi --check-deps:trace --force trc')
    t.grep('warning: uses lib1, not a dependency: <sandbox>/install/include/lib1.h')

    # declared and used: nothing reported
    t.runs('./scbi --check-deps:trace trc/ok')
    t.ngrep('not a dependency')
    t.ngrep('may not be needed')

    # the trace is in the logs of the module (one file per process)
    t.runs('ls .root/builds/trc/x86_64-linux-gnu-ok/logs/trace | wc -l')
    t.ngrep('^0$')

    # a program run: used
    t.runs('./scbi --check-deps:trace trc/tool')
    t.ngrep('may not be needed')

    # declared, not used: a note (the trace sees everything)
    t.sh('sed -i "s|    .*bin/main.*|    echo nothing|" scripts.d/trc.yaml')
    t.runs('./scbi --check-deps:trace trc/tool')
    t.grep('note: lib1 may not be needed: none of its files used')

    # a module giving a tool to the modules depending on it (its env hook
    # adds to PATH), with a library too
    t.sh('''cat > scripts.d/ptool.yaml <<'XEOF'
plugin: ptool

env:
  - add-to-var PATH $PREFIX/bin

install: |-
  mkdir -p $PREFIX/bin
  mkdir -p $PREFIX/lib
  write $PREFIX/bin/ptool:
      #!/bin/sh
      echo generated
  chmod +x $PREFIX/bin/ptool
  write $PREFIX/lib/libptool.a:
      archive
XEOF
cat > scripts.d/usetool.yaml <<'XEOF'
plugin: usetool

depends:
  - ptool

build:
  _: |-
    write main.d:
        main.o: /usr/include/stdio.h
    ptool > gen.c
  nouse: |-
    write main.d:
        main.o: /usr/include/stdio.h
XEOF''')
    t.runs('./scbi ptool')

    # without trace: the tool is not seen, not reported as unused
    t.runs('./scbi --check-deps usetool')
    t.ngrep('may not be needed')

    # with trace: the tool run (found in PATH) is seen
    t.runs('./scbi --check-deps:trace --force usetool')
    t.ngrep('may not be needed')
    t.runs('./scbi --check-deps:trace usetool/nouse')
    t.grep('note: ptool may not be needed: none of its files used')
