import re
from pathlib import Path

import pytest

from corpus import plan_files
from scbi.bashcompat import read_fields, read_lines
from scbi.plan import PlanError, PlanLoader, PlanState, check_barrier, merge_variant

# ---------------------------------------------------------------- bashcompat


def test_read_fields():
    assert read_fields("  a b  c d e f  g  ", 6) == ["a", "b", "c", "d", "e", "f  g"]
    assert read_fields("a", 3) == ["a", "", ""]
    assert read_fields("", 2) == ["", ""]
    assert read_fields("\t[ = deb,9 deb,11", 6) == ["[", "=", "deb,9", "deb,11", "", ""]


def test_read_lines_drops_unterminated_last_line():
    assert read_lines("a\nb\n") == ["a", "b"]
    assert read_lines("a\nb") == ["a"]
    assert read_lines("") == []


# ------------------------------------------------------------------- unit


@pytest.mark.parametrize(
    "cvariant, rvariant, expected",
    [
        ("default", "fast", "/fast"),
        ("a", "fast", "/fast"),
        ("a", "+fast", "/fast.a"),
        ("a.b", "+c.d", "/c.d.a.b"),
        ("a.b", "-a", "/b"),
        ("a.b.c", "-b", "/a.c"),
        ("a", "-a", ""),
        ("a", "+a", "/a"),
    ],
)
def test_merge_variant(cvariant, rvariant, expected):
    assert merge_variant(cvariant, rvariant) == expected


def test_check_barrier():
    assert check_barrier("", "", [])
    assert check_barrier("", "deb,9", ["deb", "9"])
    assert not check_barrier("", "deb,9", ["deb", "10"])
    assert check_barrier("mpi.x", "mpi", [])
    assert check_barrier("mpi", "deb,mpi", ["deb"])


def load(tmp_path: Path, text: str, nameref: str = "p", discs=(), **files) -> PlanState:
    (tmp_path / f".plan-{nameref.split('/')[0]}").write_text(text)
    for name, content in files.items():
        (tmp_path / f".plan-{name}").write_text(content)
    state = PlanState()
    PlanLoader(state, tmp_path, discs, cwd=tmp_path / "nowhere").load(nameref)
    return state


def test_simple_plan(tmp_path):
    s = load(tmp_path, "# comment\nlcms2:v2\naws/fast:#1.0\nskipme:skip\n")
    assert s.modver["lcms2"] == "lcms2:v2"
    assert s.modver["aws"] == "aws/fast:#1.0"
    assert s.modver["skipme.skip"] == "yes"
    assert s.plan_hist["lcms2"] == ";p,lcms2:v2"
    assert s.module_ref("lcms2") == ["lcms2", "default", "BRANCH", "v2"]
    assert s.module_ref("skipme") == ["skipme", "default", "NONE", "skip"]


def test_set_and_group(tmp_path):
    s = load(
        tmp_path,
        "@set V = 12\nm1:$V\n[\n  m2\n  m3/x:9\n] /fast:${V}\n",
    )
    assert s.modver["m1"] == "m1:12"
    assert s.modver["m2"] == "m2/fast:12"
    assert s.modver["m3"] == "m3/fast:12"


def test_barriers(tmp_path):
    text = "[ = deb,9 deb,11\n  a\n]\n[ /= deb,9\n  b\n]\n[ = mpi\n  c\n]\n"
    s = load(tmp_path, text, "p/mpi", discs=["deb", "11"])
    assert set(k for k in s.modver) == {"a", "b", "c"}
    s = load(tmp_path, text, "p", discs=["deb", "9"])
    assert set(s.modver) == {"a"}


def test_for_on_alias_load(tmp_path):
    s = load(
        tmp_path,
        "@load base\n@for app use lib/x:v3\n@on deb use other:v4\n@alias priv use pub\n",
        discs=["deb"],
        base="lib:v1\n",
    )
    assert s.modver["lib"] == "lib:v1"
    assert s.modver["app=lib"] == "lib/x:v3"
    assert s.modver["other"] == "other:v4"
    assert s.module_alias == {"priv": "pub"}
    assert s.module_ref("lib", "app/v:1") == ["lib", "x", "BRANCH", "v3"]
    assert s.module_ref("lib", "other") == ["lib", "default", "BRANCH", "v1"]


def test_ref_with_pattern(tmp_path):
    s = load(tmp_path, "m1/var:1.2.3\n@ref m2 as m1 version v/^([0-9]).([0-9])/\n")
    assert s.modver["m2"] == "m2/var:v12"


@pytest.mark.parametrize(
    "text, message",
    [
        ("@on deb x:1\n", "syntax error, missing use in @on"),
        ("@ref a xx b\n", "syntax error, unknown option xx in @ref"),
        ("@ref a as b\n", "b has no reference in build plan"),
        ("@set A 1\n", 'syntax error, missing "=" in @set'),
        ("[ ~ x\n]\n", "build plan unexpected ~ on group start"),
        ("[\n a\n", "build plan group is not closed .plan-p"),
    ],
)
def test_errors(tmp_path, text, message):
    with pytest.raises(PlanError) as e:
        load(tmp_path, text)
    assert e.value.message == message


def test_missing_plan(tmp_path):
    with pytest.raises(PlanError, match="build plan .plan-nope/x does not exists"):
        PlanLoader(PlanState(), tmp_path).load("nope/x")


def test_local_plan_takes_precedence(tmp_path):
    (tmp_path / ".plan-p").write_text("a:global\n")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    (cwd / ".scbi-plan-p").write_text("a:local\n")
    state = PlanState()
    PlanLoader(state, tmp_path, cwd=cwd).load("p")
    assert state.modver["a"] == "a:local"


# ----------------------------------------------------------------- oracle

DISCRIMINANT_SETS = [
    [],
    ["linux", "gnu", "deb", "debian", "12", "bookworm", "x86_64"],
    ["linux", "deb", "9"],
    ["linux", "deb", "10", "10.1", "9.3"],
    ["linux", "fed"],
    ["win", "windows"],
]

_BARRIER_RE = re.compile(r"^\s*\[\s*/?=\s+(.*)$")


def plan_variants(path: Path) -> list[str]:
    """Plan variants to try: none, and each word used in barriers."""
    found = set()
    for line in path.read_text().splitlines():
        m = _BARRIER_RE.match(line)
        if m:
            for group in m.group(1).split():
                found.update(group.split(","))
    found = sorted(v for v in found if v)
    return [""] + found + ([".".join(found[:2])] if len(found) > 1 else [])


def oracle_cases():
    cases = []
    for path in plan_files():
        name = path.name[len(".plan-") :]
        for v in plan_variants(path):
            for discs in DISCRIMINANT_SETS:
                cases.append((name + (f"/{v}" if v else ""), str(path.parent), " ".join(discs)))
    return cases


DUMP = r"""
exec 2>&1
SCBI_PLUGINS="$2"
SCBI_OS_DISCRIMINANTS=(); for d in $3; do SCBI_OS_DISCRIMINANTS[$d]=yes; done
mkdir -p /tmp/oracle-empty-cwd-$$ && cd /tmp/oracle-empty-cwd-$$
load-module-plan "$1" > /dev/null
for k in "${!SCBI_MODVER[@]}"; do printf 'M\x1f%s\x1f%s\n' "$k" "${SCBI_MODVER[$k]}"; done
for k in "${!SCBI_PLAN_HIST[@]}"; do printf 'H\x1f%s\x1f%s\n' "$k" "${SCBI_PLAN_HIST[$k]}"; done
for k in "${!SCBI_MODULE_ALIAS[@]}"; do printf 'A\x1f%s\x1f%s\n' "$k" "${SCBI_MODULE_ALIAS[$k]}"; done
for k in "${!SCBI_PLAN_LOADED[@]}"; do printf 'L\x1f%s\x1f%s\n' "$k" "${SCBI_PLAN_LOADED[$k]}"; done
echo END-OF-DUMP
"""


def parse_dump(out: str) -> dict[str, dict[str, str]]:
    res: dict[str, dict[str, str]] = {"M": {}, "H": {}, "A": {}, "L": {}}
    for line in out.splitlines():
        if "\x1f" in line:
            kind, key, value = line.split("\x1f")
            res[kind][key] = value
    return res
