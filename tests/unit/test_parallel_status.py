"""The status bar of a parallel build: every module running is shown."""

from scbi.parallel import fit_status

ITEMS = [("c-gnatcoll-bindings", "build (waiting)"), ("c-langkit-support", "config"),
         ("c-libadalang-tools", "build")]


def test_no_limit():
    assert fit_status("[1/9] ", ITEMS[:2], 0) == \
        "[1/9] c-gnatcoll-bindings: build (waiting) · c-langkit-support: config"


def test_steps_shortened():
    text = fit_status("[1/9] ", ITEMS[:2], 62)
    assert text == "[1/9] c-gnatcoll-bindings: waiting · c-langkit-support: config"


def test_names_shortened_all_shown():
    text = fit_status("[1/9] ", ITEMS, 60)
    assert len(text) <= 60, text
    #  the common prefix c- dropped, each module and its step shown
    assert text.count(" · ") == 2
    for name, step in (("gnatco", "waiting"), ("langkit", "config"), ("libada", "build")):
        assert name in text and f": {step}" in text, text
