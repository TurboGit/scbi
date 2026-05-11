from pathlib import Path
import pytest

from src.scbi.core import ScbiBuild, main, CANONICAL_STEPS
from src.scbi.models import ModuleRef, RefKind


def test_canonical_steps():
    assert "setup" in CANONICAL_STEPS
    assert "config" in CANONICAL_STEPS
    assert "build" in CANONICAL_STEPS
    assert "install" in CANONICAL_STEPS
    assert "wrapup" in CANONICAL_STEPS


def test_module_ref_parse():
    ref = ModuleRef.parse("c-gmp")
    assert ref.module == "c-gmp"
    assert ref.variant == "default"
    assert ref.kind == RefKind.NONE

    ref = ModuleRef.parse("c-gmp/release:#1.0")
    assert ref.module == "c-gmp"
    assert ref.variant == "release"
    assert ref.kind == RefKind.VERSION
    assert ref.version == "1.0"


def test_scbi_build_initialization():
    sb = ScbiBuild(
        plugins_dir=Path("tests/plugins"),
        plans_dir=Path("tests/scripts.d"),
    )
    assert sb.plugins_dir == Path("tests/plugins")
    assert sb.plans_dir == Path("tests/scripts.d")
    assert sb.bdir == Path.cwd() / ".scbi-build"


def test_module_ref_to_string():
    assert str(ModuleRef.parse("c-gmp")) == "c-gmp"
    assert str(ModuleRef.parse("c-gmp/release")) == "c-gmp/release"
    assert str(ModuleRef.parse("c-gmp:#1.0")) == "c-gmp:#1.0"
    assert str(ModuleRef.parse("c-gmp:dev")) == "c-gmp:dev"


def test_main_no_args():
    code = main([])
    assert code == 1


def test_main_help():
    code = main(["--help"])
    assert code == 0


def test_cli_args_parsing():
    """Verify ModuleRef.parse works for all ref patterns used in CLI."""
    cases = [
        ("c-gmp", "c-gmp", "default", RefKind.NONE),
        ("c-gmp/release", "c-gmp", "release", RefKind.NONE),
        ("c-gmp:#6.2.1", "c-gmp", "default", RefKind.VERSION),
        ("c-gmp:master", "c-gmp", "default", RefKind.BRANCH),
        ("c-gmp:dev", "c-gmp", "default", RefKind.DEV),
        ("c-gmp/release:#2.0", "c-gmp", "release", RefKind.VERSION),
    ]
    for ref_str, module, variant, kind in cases:
        r = ModuleRef.parse(ref_str)
        assert r.module == module, f"{ref_str}: module={r.module}"
        assert r.variant == variant, f"{ref_str}: variant={r.variant}"
        assert r.kind == kind, f"{ref_str}: kind={r.kind}"
