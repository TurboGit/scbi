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


def test_main_enable_flag():
    sb = ScbiBuild(
        plugins_dir=Path("tests/plugins"),
        enabled_features={"feature_one": "true"},
    )
    code = sb.build("c-noop")
    assert code == 0


def test_main_multiple_enable_flags():
    sb = ScbiBuild(
        plugins_dir=Path("tests/plugins"),
        enabled_features={"feature_one": "true", "feature_two": "true"},
    )
    code = sb.build("c-noop")
    assert code == 0


def test_main_enable_and_deps():
    sb = ScbiBuild(
        plugins_dir=Path("tests/plugins"),
        enabled_features={"feature": "true"},
    )
    sb.do_deps = True
    code = sb.build("c-noop")
    assert code == 0


def test_scbi_build_with_enabled_features():
    sb = ScbiBuild(
        plugins_dir=Path("tests/plugins"),
        enabled_features={"test_feature": "true"},
    )
    assert sb.enabled_features == {"test_feature": "true"}


def test_scbi_build_inherits_features_to_env():
    """Enabled features are passed to BuildEnv and accessible via is_enabled."""
    from src.scbi.build_env import BuildEnv
    sb = ScbiBuild(
        plugins_dir=Path("tests/plugins"),
        enabled_features={"my_feature": "true"},
    )
    be = BuildEnv(
        module="c-test",
        scbi_enabled_features=sb.enabled_features,
    )
    assert be.is_enabled("my-feature")
    assert not be.is_enabled("non-existent")


def test_cross_compilation_hooks_resolved():
    """c-gmp has cross-config which should be resolved when host != target."""
    from src.scbi.plugin_loader_yaml import PluginLoader
    from src.scbi.models import ModuleRef
    from src.scbi.build_env import BuildEnv
    loader = PluginLoader(Path("tests/plugins"))
    ref = ModuleRef.parse("c-gmp")
    plugin = loader.load(ref.module)
    be = BuildEnv(
        module=ref.module,
        variant=ref.variant,
        scbi_host="x86_64-linux-gnu",
        scbi_target="aarch64-linux-gnu",
        scbi_plugins=Path("tests/plugins"),
    )
    assert be.is_cross
    resolved = loader.resolve_hook(
        plugin, be.variant, "config", use_cross=True
    )
    assert resolved is not None
    config_text = " ".join(resolved)
    assert "--build=" in config_text


def test_cross_with_use_cross_false():
    """When host == target, cross hooks should not be resolved."""
    from src.scbi.plugin_loader_yaml import PluginLoader
    from src.scbi.models import ModuleRef
    loader = PluginLoader(Path("tests/plugins"))
    ref = ModuleRef.parse("c-gmp")
    plugin = loader.load(ref.module)
    resolved = loader.resolve_hook(
        plugin, ref.variant, "config", use_cross=False
    )
    assert resolved is not None
    config_text = " ".join(resolved)
    assert "--build=" not in config_text
