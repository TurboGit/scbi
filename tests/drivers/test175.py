def test(t):
    # scbi format on YAML plug-ins

    t.runs('./scbi format fixtures/format/fmt.yaml')

    t.clean_diff("""\
# Header of the plug-in (stays at the top)
# second header line

plugin: fmt

vars:
  B: '@x'

vcs:
  proxy: none
  options: none
  protocol: git
  url: /r/fmt.git

patches:
  - if ref =~ 1.0: a.diff

# Comment of depends
depends:
  - lib2  # needed for x
  # lib1 comes after
  - lib1

env:
  - add-to-var PATH $PREFIX/bin
  - set-var A "b c"

pre-config: echo pre

config:
  _: |
    # this is shell, not a YAML comment
    ./configure --prefix=$PREFIX
  default: ./configure
  # the v1 variant
  v1: ./configure --enable-v1
  cross:
    _: ./configure --host=$TARGET

# Comment of build
build: make -j4  # end of line of build

# End of file comment
""")

    # --replace rewrites the plug-in, a second run changes nothing

    t.sh('cp fixtures/format/fmt.yaml .root/fmt.yaml')

    t.runs('./scbi format --replace .root/fmt.yaml')

    t.runs('./scbi format .root/fmt.yaml')

    t.runs('diff .root/fmt.yaml <(./scbi format .root/fmt.yaml)')

    t.sh('rm -f .root/fmt.yaml')
