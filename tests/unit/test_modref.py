import pytest

from corpus import modrefs
from known_diffs import modref_has_glob
from scbi.modref import (
    ModuleRef,
    all_variants,
    has_variant,
    parse_module_ref,
)


@pytest.mark.parametrize(
    "ref, expected",
    [
        ("lcms2", ModuleRef("lcms2", "default", "NONE", "NONE")),
        ("lcms2/fast", ModuleRef("lcms2", "fast", "NONE", "NONE")),
        ("gimp=lcms2/slow", ModuleRef("gimp=lcms2", "slow", "NONE", "NONE")),
        ("lcms2:v2.0", ModuleRef("lcms2", "default", "BRANCH", "v2.0")),
        ("lcms2/fast:v2.0", ModuleRef("lcms2", "fast", "BRANCH", "v2.0")),
        ("lcms2/@:v2.0", ModuleRef("lcms2", "@", "BRANCH", "v2.0")),
        ("lcms2:#v1.0", ModuleRef("lcms2", "default", "VERSION", "v1.0")),
        ("lcms2:dev", ModuleRef("lcms2", "default", "DEV", "dev")),
        ("lcms2:skip", ModuleRef("lcms2", "default", "BRANCH", "skip")),
        ("mod/mpi.openmp", ModuleRef("mod", "mpi.openmp", "NONE", "NONE")),
    ],
)
def test_parse_module_ref(ref, expected):
    assert parse_module_ref(ref) == expected


def test_variants():
    assert all_variants("default") == []
    assert all_variants("mpi") == ["mpi"]
    assert all_variants("mpi.openmp") == ["mpi", "openmp"]
    assert parse_module_ref("m/a.b").variants == ["a", "b"]
    assert has_variant("a.b", "b")
    assert not has_variant("a.b", "c")
    assert not has_variant("default", "default")


def test_to_bash_array_drops_empty_fields():
    assert parse_module_ref("a:").to_bash_array() == ["a", "default", "BRANCH"]


@pytest.mark.oracle
def test_parse_module_ref_oracle(oracle):
    refs = [r for r in modrefs() if not modref_has_glob(r)]
    expected = oracle.batch(
        'parse-module-ref R "$1"; printf "%s\\n" "${R[@]}"', [(r,) for r in refs]
    )
    for ref, out in zip(refs, expected):
        assert parse_module_ref(ref).to_bash_array() == out.splitlines(), ref


@pytest.mark.oracle
def test_all_variants_oracle(oracle):
    values = ["default", "a", "a.b", "a.b.c", "a..b", ".a", "a.", "native", "auto.fast"]
    expected = oracle.batch(
        'all-variants-v R "$1"; printf "%s\\n" "${R[@]}"', [(v,) for v in values]
    )
    for v, out in zip(values, expected):
        assert all_variants(v) == [x for x in out.splitlines() if x], v


@pytest.mark.oracle
def test_has_variant_oracle(oracle):
    cases = [(vs, v) for vs in ["default", "a", "a.b", "native.x"] for v in ["a", "b", "x", "default"]]
    expected = oracle.batch('has-variant "$1" "$2" && echo yes || echo no', cases)
    for (vs, v), out in zip(cases, expected):
        assert has_variant(vs, v) == (out.strip() == "yes"), (vs, v)
