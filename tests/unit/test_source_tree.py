"""The source-tree hook: YAML, checks, the excludes of the entries."""

import pytest

from scbi.plugin import construct, yamlfmt
from scbi.plugin.construct import DefinitionError, source_entry
from scbi.plugin.lint import ERROR, WARNING, lint_text
from scbi.plugin.model import Guarded, HookKey, SourceEntry, Values
from scbi.plugin.yamlwrite import format_text
from scbi.steps.generic import later_targets

GNAT = """plugin: p

vcs:
  proxy: default
  options: none
  protocol: git
  url: /r/gnat

source-tree:
  - from: gcc
  - to: gcc/ada
  - if cross:
      - from: iface
        to: gcc/ada/gcc-interface
        exclude:
          - doc
          - tests/old

depends:
  - gcc
  - iface
"""


def test_yaml_round_trip_and_canonical(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text(GNAT)
    pdef = yamlfmt.load(f)
    assert pdef.hooks[HookKey("source-tree")] == Values((
        SourceEntry("gcc"), SourceEntry("", "gcc/ada"),
        Guarded("cross", (SourceEntry("iface", "gcc/ada/gcc-interface", ("doc", "tests/old")),))))
    assert format_text("p", GNAT) == GNAT
    #  the canonical order of the keys of an entry, a single entry as a mapping
    assert format_text("p", "plugin: p\nsource-tree:\n  - exclude: [a]\n    to: b\n    from: m\n") == \
        "plugin: p\n\nsource-tree:\n  - from: m\n    to: b\n    exclude:\n      - a\n"
    f.write_text("plugin: p\nsource-tree:\n  from: m\n")
    assert yamlfmt.load(f).hooks[HookKey("source-tree")] == Values((SourceEntry("m"),))


@pytest.mark.parametrize("fields, message", [
    ({"form": "m"}, "unknown keys"),
    ({"from": "a b"}, "a module name"),
    ({"to": "../x"}, "'..' is not allowed"),
    ({"to": "/abs"}, "relative"),
    ({"exclude": ["."]}, "root of the sources"),
    ({"exclude": [1]}, "a list of paths"),
])
def test_entry_errors(fields, message):
    with pytest.raises(DefinitionError, match=message):
        source_entry(fields)


def test_entry_normalized():
    assert source_entry({"to": "./gcc//ada/", "exclude": "x/"}) == SourceEntry("", "gcc/ada", ("x",))
    assert construct.is_source_entry("source-tree", {"from": "m"})
    assert not construct.is_source_entry("source-tree", {"cross": []})


def test_later_targets():
    e = [SourceEntry("gcc"), SourceEntry("", "gcc/ada"), SourceEntry("iface", "gcc/ada/gcc-interface"),
         SourceEntry("doc", "docs")]
    assert later_targets(e, 0) == ["gcc/ada", "gcc/ada/gcc-interface", "docs"]
    assert later_targets(e, 1) == ["gcc-interface"]
    assert later_targets(e, 2) == []
    #  a later entry at the same place or above: not an exclude
    assert later_targets([SourceEntry("a", "x"), SourceEntry("b", "x"), SourceEntry("c", ".")], 0) == []


def issues(text):
    return [(i.level, i.where, i.message) for i in lint_text("p", text)]


def test_lint():
    assert issues(GNAT) == []
    text = GNAT.replace("  - iface\n", "")
    assert issues(text) == [(ERROR, "source-tree", "iface is not a dependency (depends, build-depends)")]
    #  a dependency of any qualifier, build-depends too
    text = GNAT.replace("depends:\n  - gcc\n  - iface\n", "depends:\n  v: [gcc]\nbuild-depends: [iface]\n")
    assert issues(text) == []
    text = """plugin: p
vcs: {proxy: default, options: none, protocol: git, url: /r/p}
depends: [a, b]
source-tree:
  - from: a
    to: x
  - from: b
    to: x
  - from: a
    to: y/z
  - from: b
    to: y
"""
    found = issues(text)
    assert (ERROR, "source-tree", "several entries copied to x") in found
    assert (WARNING, "source-tree", "the entry of a (y/z) is replaced by the later entry of b (y)") in found
    assert (WARNING, "source-tree", "no entry for the sources of the module (an entry without from): unused") in found
