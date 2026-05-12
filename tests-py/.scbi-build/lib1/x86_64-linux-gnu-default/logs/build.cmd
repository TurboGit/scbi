# scbi replay: build
# date: 2026-05-12 07:30:37.608325
# prefix: /home/obry/dev/git/scbi-opencode/tests-py/.scbi-build/install
# target: x86_64-linux-gnu
# variant: default
# TVDIR: /home/obry/dev/git/scbi-opencode/tests-py/.scbi-build/lib1/x86_64-linux-gnu-default
(
  cd /home/obry/dev/git/scbi-opencode/tests-py
  export C_INCLUDE_PATH=/home/obry/dev/git/scbi-opencode/tests-py/include:/home/obry/dev/builds/c-libiconv/x86_64-linux-gnu-default/install/include
  export LD_LIBRARY_PATH=.:/home/obry/dev/git/scbi-opencode/tests-py/lib:/home/obry/dev/builds/c-gnatcoll-bindings-gmp/x86_64-linux-gnu-default/install/lib:/home/obry/dev/builds/c-gnatcoll-bindings-iconv/x86_64-linux-gnu-default/install/lib:/home/obry/dev/builds/c-libiconv/x86_64-linux-gnu-default/install/lib:/home/obry/dev/builds/c-gnatcoll-core/x86_64-linux-gnu-default/install/lib:/home/obry/dev/builds/c-gpr2-lib/x86_64-linux-gnu-default/install/lib:/home/obry/dev/builds/c-adasat/x86_64-linux-gnu-default/install/lib:/home/obry/dev/builds/c-libgpr/x86_64-linux-gnu-default/install/lib:/home/obry/dev/builds/c-xmlada/x86_64-linux-gnu-default/install/lib
  export LIBRARY_PATH=.:/home/obry/dev/git/scbi-opencode/tests-py/lib:/home/obry/dev/builds/c-libiconv/x86_64-linux-gnu-default/install/lib
  export PATH=/home/obry/.opencode/bin:/home/obry/.opam/default/bin:/home/obry/.config/Code/User/globalStorage/github.copilot-chat/debugCommand:/home/obry/.config/Code/User/globalStorage/github.copilot-chat/copilotCli:/home/obry/.opencode/bin:/home/obry/.opam/default/bin:/home/obry/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games:/home/obry/.fzf/bin

  rm -f *.o
  make --no-print-directory
)
