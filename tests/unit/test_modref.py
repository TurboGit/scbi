import pytest

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
