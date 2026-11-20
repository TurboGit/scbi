def test(t):
    # scbi lint knows the variables set by the environment of the
    # with-variants (native) of the dependencies.

    t.sh("""\
cat > scripts.d/nat.yaml <<'END'
plugin: nat

with-variants:
  native:
    packages:
      - gcc
    env:
      - set-var LPATH /some/path

env:
  _:
    - set-var LPATHENV /toto
END
cat > scripts.d/main.yaml <<'END'
plugin: main

build-depends:
  default:
    - nat

config-options:
  - -DLIB=$LPATH

config: cmake -DLIB=$LPATH -DLIB=$LPATHENV
END
printf 'nat/native\\nmain\\n' > scripts.d/.plan-nat
""")

    t.runs("./scbi lint --plan=nat main")
    t.ngrep("warning")
