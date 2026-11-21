"""scbi lint checks (scbi.plugin.lint): one case per check."""

import pytest

from scbi.plugin.lint import ERROR, WARNING, assigned, lint_text, referenced


def issues(text, name="p"):
    return [(i.level, i.where, i.message) for i in lint_text(name, text)]


def test_clean_plugin():
    text = """
plugin: p
vars: {MYVAR: x}
vcs: {proxy: none, options: none, protocol: git, url: /r/p.git}
depends: [lib1]
env:
  - add-to-var PATH $PREFIX/bin
  - set-var P_HOME $PREFIX
config: |
  ../src/configure --prefix=$PREFIX --host=$TARGET $MYVAR $P_HOME
  for f in a b:
      echo $f
  X = 1
  echo $X $SCBI_JOBS $PATH
archive:
  - default
  - none
  - cp
  - /store
  - p-$VERSION.tgz
out-of-tree: false
"""
    assert issues(text) == []


@pytest.mark.parametrize("text, expected", [
    ("confg: make\n", (ERROR, "confg", "unknown hook 'confg', did you mean 'config'?")),
    ("plugin: q\n", (ERROR, "plugin", "plugin name 'q' does not match the file name 'p'")),
    ("config: {common: make}\n", (ERROR, "config.common", "'common' is only allowed for cumulative hooks")),
    ("env: {cross: {cross: [set-var A b]}}\n", (ERROR, "env.cross.cross", "nested cross")),
    ("vcs: {proxy: none, options: none}\n", (ERROR, "vcs", "missing fields ['protocol', 'url']")),
    ("out-of-tree: maybe\n", (ERROR, "out-of-tree", "'maybe' is not one of true/false")),
    ("aggregate: all\n", (ERROR, "aggregate", "'all' is not one of direct/recursive/no")),
    ("env: [frob-var A b]\n", (ERROR, "env", "unknown environment action 'frob-var'")),
    ("patches: [{'if ref ==': a.diff}]\n", None),
    ("depends: ['$(get-thing)']\n", None),
    ("config: [make]\n", (ERROR, "config", "a body in the command language (string) is expected")),
])
def test_errors(text, expected):
    found = issues(text)
    errors = [i for i in found if i[0] == ERROR]
    assert errors, found
    if expected:
        assert expected in errors


def test_all_problems_reported():
    text = "confg: make\nbuld: make\nconfig: {common: x, v1: '', cross: {common: y}}\n"
    found = issues(text)
    assert [i[1] for i in found if i[0] == ERROR] == ["confg", "buld", "config.common", "config.cross.common"]
    assert (WARNING, "config.v1", "defined but empty") in found


@pytest.mark.parametrize("text, expected", [
    ("config: echo $VERSION\n", "VERSION is a parameter of archive, not of config"),
    ("build: echo $KIND\n", "KIND is a parameter of patches, not of build"),
    ("build: echo $UNKNOWN\n", "variable UNKNOWN is not known in this hook"),
    ("depends: [$FOO]\n", "variable FOO is not known in this hook"),
    ("env: [set-var A $BAR]\n", "variable BAR is not known in this hook"),
    ("functions: {f: echo $NOPE}\n", "variable NOPE is not known in this hook"),
    ("install: ''\n", "defined but empty"),
    ("depends: []\n", "defined but empty"),
])
def test_warnings(text, expected):
    found = issues(text)
    assert [i for i in found if i[0] == ERROR] == []
    assert any(i[0] == WARNING and i[2] == expected for i in found), found


def test_not_reported():
    text = """
functions:
  helper: {params: [A], run: echo $A $PREFIX}
env: [set-var FROM_ENV x]
build: |
  echo '$NOT_EXPANDED' \\$ESCAPED $FROM_ENV  # $IN_COMMENT
  read -r L1 L2 < f; echo $L1 $L2 $log $1 $@ $? ${#ARR[@]}
  declare -a ARR=(); export E=1; echo ${E:-x}
version: echo $VERSION_OK
"""
    assert issues(text) == []


def test_yaml_errors():
    assert issues("a: [\n")[0][0] == ERROR
    assert issues("- a\n") == [(ERROR, "yaml", "a mapping is expected")]


def test_helpers():
    assert referenced("$A ${B} ${#C} \\$D $E1") == ["A", "B", "C", "E1"]
    assert assigned("A=1; local B C=2; read -r D E; for F in x; do :; done; X[1]=2") >= {"A", "B", "C", "D", "E", "F", "X"}


def test_local_variables_and_if():
    text = """
config-options:
  _:
    - BT = get-build-type CMAKE Release
    - -DA=$(if $BT == Debug then ON else OFF)
    - -DB=$(uppercase $VARIANT)
env:
  - L = lowercase $VARIANT
  - set-var LIBNAME lib$L
"""
    assert issues(text) == []
    #  a syntax error of $(if ...) is reported
    bad = issues("config-options:\n  - -DA=$(if variant == x ON)\n")
    assert bad and bad[0][0] == ERROR


def test_build_target_hook():
    assert issues("build: make\nbuild-runtime: make rts\n") == []
    assert issues("build-env: [system-compiler]\nbuild-x-build-y: make\n")[0][0] == ERROR


def test_log_level():
    text = """
plugin: p
functions:
  f:
    run: log x f
build: |
  log 1 ok
  log $SCBI_JOBS from a variable
  if cross:
      log 0 bad
  write f:
      log 0 the text of a file
"""
    assert issues(text) == [(ERROR, "build", "line 4: log: level must be an integer >= 1"),
                            (ERROR, "function f", "line 1: log: level must be an integer >= 1")]


def test_out_of_tree_in_meta_module():
    meta = "plugin: p\nmodules: [lib1]\nout-of-tree: false\n"
    assert issues(meta) == [(WARNING, "out-of-tree", "not used by a meta-module (no sources)")]
    #  with sources (a meta-module for some variants only): not flagged
    assert issues(meta + "vcs: {proxy: none, options: none, protocol: git, url: /r/p.git}\n") == []
    assert issues("plugin: p\nout-of-tree: false\n") == []


def test_environment_variables():
    text = """
plugin: p
build-env:
  - set-var LV 9
config-options:
  - -DVAR=${VAR}
  - -DLV=$LV
config: cmake $(config-options) ../src
"""
    assert issues(text) == [(WARNING, "config-options", "variable VAR is not known in this hook")]
    #  set by the environment file
    assert [(i.level, i.where, i.message) for i in lint_text("p", text, known=frozenset({"VAR"}))] == []


def test_unused_variables():
    text = """
plugin: p
functions:
  show:
    run: echo $FROMHOOK
config: |-
  CDEBUG = is-enabled cmake-debug
  OPTIONS =
  OPTIONS = config-options
  USED = a
  export EXPORTED = b
  FROMHOOK = c
  if exists(x):
      INNER = d
  for F in a b:
      echo ${USED:-x} $F
  show
  write out.txt:
      $OPTIONS
"""
    #  (the function reading a variable of its caller is reported as
    #  using an unknown variable)
    assert issues(text) == [(WARNING, "config", "line 1: variable CDEBUG is set but never used"),
                            (WARNING, "config", "line 8: variable INNER is set but never used"),
                            (WARNING, "function show", "variable FROMHOOK is not known in this hook")]
    #  in a function too
    text = "plugin: p\nfunctions:\n  f:\n    run: |-\n      X = 1\n      echo x\n"
    assert issues(text) == [(WARNING, "function f", "line 1: variable X is set but never used")]


def test_dependency_vars(tmp_path):
    from scbi.plugin.lint import dependency_vars

    files = {
        "a": "plugin: a\nenv:\n  - set-var A 1\n  - if cross: add-to-var A_CROSS x\nbuild-env:\n  - set-var A_BUILD 1\n"
             "depends:\n  - b/v:1\n  - os@-zlib\n  - $DYN\n",
        "b": "plugin: b\nenv:\n  _: [set-var B 1]\n  v: [prepend-to-var B_V x]\ndepends: [a, missing]\n"
             "with-variants:\n  native:\n    packages: [gcc]\n    env: [set-var B_NATIVE /p]\n",
        "p": "plugin: p\nvars: {PV: x}\ntests-env: [set-var PT 1]\n",
    }
    for n, text in files.items():
        (tmp_path / f"{n}.yaml").write_text(text)
    find = lambda n: tmp_path / f"{n}.yaml" if (tmp_path / f"{n}.yaml").is_file() else None
    data = {"plugin": "m", "inherit": [{"from": "p"}], "build-depends": {"common": ["a"]}}
    #  env of the dependencies (recursively, cycle a <-> b, all qualifiers
    #  and guards, the env of the with-variants), not their build-env; vars
    #  and env hooks of the parents
    assert dependency_vars("m", data, find) == {"A", "A_CROSS", "B", "B_V", "B_NATIVE", "PV", "PT"}


def test_positions():
    #  the line and column (1-based) of each issue in the file: the key of
    #  the hook, the variable, the line of a command body
    text = """plugin: p

functions:
  f:
    run: |-
      X = 1
      echo x

config-options:
  common:
    - -DA=$NOPE

config: |-
  CDEBUG = is-enabled cmake-debug
  echo $VERSION
  log 0 bad

out-of-tre: true
build:
"""
    lines = text.splitlines()
    found = {(i.line, i.column): lines[i.line - 1][i.column - 1:].split()[0] for i in lint_text("p", text)}
    assert found == {(11, 11): "$NOPE", (15, 8): "$VERSION", (16, 3): "log", (14, 3): "CDEBUG",
                     (18, 1): "out-of-tre:", (19, 1): "build:", (6, 7): "X"}
    #  YAML error: its own position
    [issue] = lint_text("p", "a: [\n")
    assert (issue.where, issue.line, issue.column) == ("yaml", 2, 1)


def test_write_blocks():
    #  no expansion in write-raw / append-raw: $NAME is not a variable;
    #  in a write block the quotes are literal (an apostrophe does not hide
    #  the next lines)
    text = """
plugin: p
build: |-
  write-raw run.sh:
      #!/bin/sh
      echo "$HOME $RAWVAR"
  append-raw run.sh:
      exit $STATUS_RAW
  write README:
      don't use $UNKNOWN1
  echo $UNKNOWN2
"""
    assert issues(text) == [(WARNING, "build", "variable UNKNOWN1 is not known in this hook"),
                            (WARNING, "build", "variable UNKNOWN2 is not known in this hook")]
    #  a variable only written in a raw block is not read
    text = "plugin: p\nbuild: |-\n  X = 1\n  write-raw f:\n      $X\n"
    assert issues(text) == [(WARNING, "build", "line 1: variable X is set but never used")]
