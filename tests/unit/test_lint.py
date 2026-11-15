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
