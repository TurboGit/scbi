"""The status bar of a parallel build: every module running is shown."""

from scbi.parallel import fit_status

ITEMS = [("c-gnatcoll-bindings", "build (waiting)"), ("c-langkit-support", "config"),
         ("c-libadalang-tools", "build")]


def test_no_limit():
    #  a letter per step, … waiting for a build slot, the common prefix
    #  c- dropped
    assert fit_status("[1/9] ", ITEMS[:2], 0) == \
        "[1/9] gnatcoll-bindings:B…  langkit-support:C"


def test_spinner():
    #  a running step followed by the frame of the spinner, a waiting one
    #  by … whatever the frame; the width does not change
    one = fit_status("[1/9] ", ITEMS, 0, 1, "abcd")
    assert one == "[1/9] gnatcoll-bindings:B…  langkit-support:Cb  libadalang-tools:Bb"
    two = fit_status("[1/9] ", ITEMS, 0, 6, "abcd")
    assert two == "[1/9] gnatcoll-bindings:B…  langkit-support:Cc  libadalang-tools:Bc"
    assert len(one) == len(two)


def test_unknown_step():
    assert fit_status("[1/9] ", [("c-foo", "vcs"), ("c-bar", "tests")], 0, 0, "ab") == \
        "[1/9] foo:vcsa  bar:Ta"


def test_names_shortened_all_shown():
    text = fit_status("[1/9] ", ITEMS, 40, 0)
    assert len(text) <= 40, text
    #  each module and its step shown
    assert text.count("  ") == 2
    for name, step in (("gnatco", "B…"), ("langki", "C⠋"), ("libada", "B⠋")):
        assert name in text and f":{step}" in text, text
