"""Canonical writer of YAML plug-ins (scbi format, the converter)."""

from pathlib import Path

import pytest

from corpus import plugin_files
from oracle import REPO_ROOT
from scbi.convert import convert
from scbi.plugin import catalog, yamlfmt
from scbi.plugin.yamlwrite import format_text, load_data

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "format" / "fmt.yaml"


def converted():
    result = []
    for f in plugin_files():
        text, _ = convert(Path(f))
        if text is not None:
            result.append((Path(f).name, text))
    return result


@pytest.fixture(scope="module")
def corpus():
    return converted()


def test_converted_plugins_canonical_and_stable(corpus):
    assert len(corpus) > 140
    for name, text in corpus:
        #  the converter writes the canonical form
        assert format_text(name, text) == text, name
        data = load_data(text)
        order = {k: i for i, k in enumerate(catalog.FORMAT_ORDER)}
        keys = [order[k] for k in data]
        assert keys == sorted(keys), name
        #  the same plug-in model
        assert yamlfmt.from_data(name, load_data(format_text(name, text))) == yamlfmt.from_data(name, data)


def test_fixture_comments_and_order():
    text = FIXTURE.read_text()
    out = format_text("fmt", text)
    assert format_text("fmt", out) == out
    assert load_data(out) == load_data(text)
    lines = out.splitlines()
    #  every comment line of the source is kept (shell lines included)
    src_comments = sorted(line.split("#", 1)[1].strip() for line in text.splitlines() if "#" in line)
    out_comments = sorted(line.split("#", 1)[1].strip() for line in lines if "#" in line)
    assert out_comments == src_comments
    assert lines[0] == "# Header of the plug-in (stays at the top)"
    assert lines[-1] == "# End of file comment"
    #  comments moved with their keys
    i = lines.index("# Comment of build")
    assert lines[i + 1] == "build: make -j4  # end of line of build"
    i = lines.index("  # the v1 variant")
    assert lines[i + 1] == "  v1: ./configure --enable-v1"
    i = lines.index("  # lib1 comes after")
    assert lines[i + 1] == "  - lib1"
    #  qualifiers: _, default, variants, cross
    cfg = lines.index("config:")
    assert [ln.split(":")[0].strip() for ln in lines[cfg + 1:] if ln.startswith("  ") and not ln.startswith("    ")
            and not ln.strip().startswith("#")][:4] == ["_", "default", "v1", "cross"]


@pytest.mark.parametrize("text", [
    "plugin: p\nbuild: |\n  a\n\n  b\n",                   # blank line in a block
    "build: |-\n  no final newline\n",
    "vars: {A: \"  leading blank\\nx\\n\"}\n",              # not a literal block
    "build: \"trailing  \\nx\\n\"\n",
    "vars: {A: '', B: '*x', C: 'a: b', D: '# x'}\n",
    "env: [{'if on debian': [set-var A b, set-var C d]}]\n",
    "inherit: [{name: n, from: p, hooks: [config]}]\n",
])
def test_round_trip(text):
    out = format_text("p", text)
    assert load_data(out) == load_data(text)
    assert format_text("p", out) == out


def test_invalid_plugin_not_formatted():
    with pytest.raises(yamlfmt.FormatError):
        format_text("p", "confg: make\n")
