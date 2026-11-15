
from scbi.bashenv import ShellVars
from scbi.ini import IniDB

INI_SAMPLES = {
    "sections": """
stat = yes

[sc]
   setup = yes
   config = yes
   build = no

[full]
   update = yes
   force = yes

[common]
   modules = test2
""",
    "multi": """
[lib1]
   modules = lib1
   tests = only
   modules = lib2 lib3
   enable = feat-a
   enable = feat-b
   options = --deps

[stest]
   tests-list = "opt1 opt2"

[common]
   quiet = yes
""",
    "quirks": """
# a comment
   # indented comment
key=value
spaced key = with space
a=b=c
plus = tail+ \n\
empty =
=novalue
[ws ]
x = $HOME/dir
y = ${SCBI_X:-dflt}
z = $(echo sub)
""",
    "no-final-newline": "a = 1\n[s]\nb = 2",
}


def load(tmp_path, text):
    p = tmp_path / "ini"
    p.write_text(text)
    db = IniDB()
    db.load_file(p)
    return db


def test_sections_and_multi_keys(tmp_path):
    db = load(tmp_path, INI_SAMPLES["multi"])
    assert db.db["lib1.modules"] == " lib1  lib2 lib3 "
    assert db.db["lib1.enable"] == " feat-a  feat-b "
    assert db.db["common.quiet"] == " yes"


def test_get_option_precedence(tmp_path):
    db = load(tmp_path, INI_SAMPLES["sections"])
    sv = ShellVars()
    assert db.get_option("sc", "setup", sv) == "yes"
    assert db.get_option("sc", "modules", sv) == "test2"  # from [common]
    assert db.get_option("", "modules", sv) == ""  # common only for a section
    assert db.get_option("sc", "stat", sv) == "yes"  # root value
    assert db.get_option("full", "nothing", sv) == ""


def test_get_option_expansion(tmp_path):
    db = load(tmp_path, INI_SAMPLES["quirks"])
    sv = ShellVars({"HOME": "/home/me"}, {"HOME"})
    assert db.get_option("ws ", "x", sv) == "/home/me/dir"
    assert db.get_option("ws ", "y", sv) == "dflt"
    assert db.get_option("ws ", "z", sv) == "sub"


def test_last_line_without_newline_ignored(tmp_path):
    db = load(tmp_path, INI_SAMPLES["no-final-newline"])
    assert db.db == {"a": " 1"}


DUMP = r"""
printf '%s' "$1" > ini-under-test
SCBI_INI_DB=()
ini-load-file ini-under-test
for k in "${!SCBI_INI_DB[@]}"; do printf '%s\x1f%s\n' "$k" "${SCBI_INI_DB[$k]}"; done
"""


EXPAND_VALUES = [
    "plain", "a  b   c", "$SCBI_X", "${SCBI_X}", "x${SCBI_X}y", "$SCBI_SP", "a${SCBI_SP}b",
    '"$SCBI_SP"', "'$SCBI_X'", '"a  b"', "~", "~/dir", "x~", "${SCBI_NONE:-dflt}",
    "${SCBI_X%env}", "${SCBI_X#from}", "$SCBI_NONE", '""', "a '' b", "$(echo  one   two)",
    "pre$(printf %s x)post", "\\$SCBI_X", "a\\ b", "*.nomatch", "ini-*", "$HOME/x",
    '"$(echo a  b)"', "a#b", "a #comment",
]
