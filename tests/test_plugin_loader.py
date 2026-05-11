from pathlib import Path
import pytest

from src.scbi.models import (
    InheritMapping,
    ParsedHookKey,
    Plugin,
    PluginError,
    PluginNotFoundError,
    PluginSyntaxError,
)
from src.scbi.plugin_loader_yaml import (
    PluginLoader,
    parse_hook_key,
    SCBI_BASE_HOOKS,
)

PLUGIN_DIR = Path(__file__).resolve().parent / "plugins"


@pytest.fixture
def ld():
    return PluginLoader(PLUGIN_DIR)


# -----------------------------------------------------------------------
# parse_hook_key
# -----------------------------------------------------------------------

def test_parse_base_hook():
    r = parse_hook_key("config")
    assert r.base_hook == "config"
    assert r.variant == ""
    assert r.modifier == ""
    assert r.cross is False


def test_parse_variant_hook():
    r = parse_hook_key("release-config")
    assert r.base_hook == "config"
    assert r.variant == "release"


def test_parse_pre_hook():
    r = parse_hook_key("pre-config")
    assert r.base_hook == "config"
    assert r.variant == ""
    assert r.modifier == "pre"


def test_parse_post_hook():
    r = parse_hook_key("post-install")
    assert r.base_hook == "install"
    assert r.modifier == "post"


def test_parse_cross_hook():
    r = parse_hook_key("cross-config")
    assert r.base_hook == "config"
    assert r.cross is True


def test_parse_variant_pre_hook():
    r = parse_hook_key("vcs-pre-config")
    assert r.base_hook == "config"
    assert r.variant == "vcs"
    assert r.modifier == "pre"


def test_parse_variant_cross():
    r = parse_hook_key("vcs-cross-config")
    assert r.base_hook == "config"
    assert r.variant == "vcs"
    assert r.cross is True


def test_parse_pre_cross():
    r = parse_hook_key("pre-cross-build")
    assert r.base_hook == "build"
    assert r.modifier == "pre"
    assert r.cross is True


def test_parse_variant_pre_cross():
    r = parse_hook_key("relaxclang-pre-cross-config")
    assert r.base_hook == "config"
    assert r.variant == "relaxclang"
    assert r.modifier == "pre"
    assert r.cross is True


def test_parse_multiword_hook():
    r = parse_hook_key("config-options")
    assert r.base_hook == "config-options"
    assert r.variant == ""


def test_parse_variant_multiword():
    r = parse_hook_key("release-config-options")
    assert r.base_hook == "config-options"
    assert r.variant == "release"


def test_parse_common_build_depends():
    r = parse_hook_key("common-build-depends")
    assert r.base_hook == "build-depends"
    assert r.variant == "common"


def test_parse_variant_build_env():
    r = parse_hook_key("clang-build-env")
    assert r.base_hook == "build-env"
    assert r.variant == "clang"


def test_parse_all_known_hooks():
    for hook in SCBI_BASE_HOOKS:
        r = parse_hook_key(hook)
        assert r.base_hook == hook
        assert r.variant == ""
        assert r.modifier == ""
        assert r.cross is False


def test_parse_unknown_hook():
    with pytest.raises(PluginSyntaxError):
        parse_hook_key("unknown-hook-name")


def test_parse_dotted_variant():
    r = parse_hook_key("variant1.variant2-config")
    assert r.base_hook == "config"
    assert r.variant == "variant1.variant2"


# -----------------------------------------------------------------------
# YAML loading
# -----------------------------------------------------------------------

def test_load_simple(ld):
    p = ld.load("c-simple")
    assert p.name == "c-simple"
    assert p.out_of_tree is True
    assert "config" in p.hooks
    assert p.hooks["config"] == ["./configure --prefix=$PREFIX"]


def test_load_gmp(ld):
    p = ld.load("c-gmp")
    assert p.name == "c-gmp"
    assert p.out_of_tree is False
    assert "vcs" in p.hooks
    assert "cross-config" in p.hooks
    assert "vcs-pre-config" in p.hooks


def test_load_not_found(ld):
    with pytest.raises(PluginNotFoundError):
        ld.load("nonexistent")


# -----------------------------------------------------------------------
# Meta modules
# -----------------------------------------------------------------------

def test_meta_module(ld):
    p = ld.load("c-meta")
    assert p.modules is not None
    assert "c-sub-a" in p.modules
    assert "c-sub-b" in p.modules
    assert "aggregate" in p.hooks


# -----------------------------------------------------------------------
# Inheritance
# -----------------------------------------------------------------------

def test_inherit_simple(ld):
    p = ld.load("c-child")
    assert p.hooks["config"] == ["cmake -DCMAKE_INSTALL_PREFIX=$PREFIX .."]
    assert p.hooks["install"] == ["make install DESTDIR=$PREFIX"]
    assert p.hooks["build"] == ["make"]
    assert isinstance(p.hooks.get("env"), dict)


def test_inherit_chain(ld):
    p = ld.load("c-grandchild")
    assert p.hooks["build"] == ["ninja"]
    assert p.hooks["config"] == ["cmake -DCMAKE_INSTALL_PREFIX=$PREFIX .."]
    assert isinstance(p.hooks.get("env"), dict)


def test_inherit_no_variant(ld):
    p = ld.load("c-no-variant-inherit")
    assert p.hooks["config"] == ["./configure --prefix=$PREFIX --enable-foo"]
    assert p.hooks["build"] == ["make"]
    assert isinstance(p.hooks.get("env"), dict)


# -----------------------------------------------------------------------
# resolve_hook
# -----------------------------------------------------------------------

def test_resolve_base(ld):
    r = ld.resolve_hook(ld.load("c-simple"), "default", "config")
    assert r == ["./configure --prefix=$PREFIX"]


def test_resolve_not_found(ld):
    assert ld.resolve_hook(ld.load("c-simple"), "default", "nonexistent") is None


def test_resolve_variant_specific(ld):
    p = ld.load("c-with-variants")
    r = ld.resolve_hook(p, "release", "config-options")
    assert r is not None
    assert r[0] == "-DCMAKE_BUILD_TYPE=Release"


def test_resolve_falls_back_to_base(ld):
    p = ld.load("c-with-variants")
    r = ld.resolve_hook(p, "release", "build-env")
    assert r is not None
    assert isinstance(r, dict)
    assert "set-var" in r
    assert r["set-var"] == ["CMAKE_C_COMPILER", "gcc"]


def test_env_hook_structured(ld):
    p = ld.load("c-meta")
    env = p.hooks.get("env")
    assert isinstance(env, dict)
    assert "add-to-var" in env
    assert env["add-to-var"] == ["PATH", "$PREFIX/bin"]


def test_build_env_structured(ld):
    p = ld.load("c-with-variants")
    r = ld.resolve_hook(p, "clang", "build-env")
    assert isinstance(r, dict)
    assert r == {"set-var": ["CMAKE_C_COMPILER", "clang-16"]}


def test_resolve_clang_config_options_none(ld):
    p = ld.load("c-with-variants")
    assert ld.resolve_hook(p, "clang", "config-options") is None


def test_resolve_dotted_uses_first_component(ld):
    p = ld.load("c-with-variants")
    r = ld.resolve_hook(p, "release.clang", "config-options")
    assert r is not None


def test_resolve_cross(ld):
    p = ld.load("c-gmp")
    r = ld.resolve_hook(p, "default", "config", use_cross=True)
    assert r is not None
    assert "--host=$TARGET" in r[0]


# -----------------------------------------------------------------------
# resolve_all_hooks
# -----------------------------------------------------------------------

def test_resolve_all_variant(ld):
    p = ld.load("c-with-variants")
    results = ld.resolve_all_hooks(p, "release", "config-options")
    assert len(results) >= 2
    flat = [cmd for sublist in results for cmd in sublist]
    assert any("-DCMAKE_BUILD_TYPE=Release" in cmd for cmd in flat)
    assert any("-DCMAKE_INSTALL_PREFIX=$PREFIX" in cmd for cmd in flat)


# -----------------------------------------------------------------------
# Variants extraction
# -----------------------------------------------------------------------

def test_variants_extracted(ld):
    p = ld.load("c-with-variants")
    assert "release" in p.variants
    assert "debug" in p.variants
    assert "clang" in p.variants


# -----------------------------------------------------------------------
# with-variant
# -----------------------------------------------------------------------

def test_with_variant_generates_empty_hooks(ld):
    p = ld.load("c-auto")
    assert "native" in p.variants
    assert "native-config" in p.hooks
    assert p.hooks["native-config"] == []
    assert "native-build" in p.hooks
    assert p.hooks["native-build"] == []
    assert "native-install" in p.hooks
    assert p.hooks["native-install"] == []
    assert "native-vcs" in p.hooks
    assert p.hooks["native-vcs"] == ["none"]
    assert "native-archive" in p.hooks
    assert p.hooks["native-archive"] == ["none"]
    assert "native-prefix" in p.hooks
    assert p.hooks["native-prefix"] == ["NONE"]


def test_with_variant_pre_post_cross_hooks(ld):
    p = ld.load("c-auto")
    for base in ("config", "build", "install"):
        for suffix in ("", "pre-", "post-", "cross-", "cross-pre-", "cross-post-"):
            key = f"native-{suffix}{base}" if suffix else f"native-{base}"
            assert key in p.hooks, f"Missing hook: {key}"
            assert p.hooks[key] == []


def test_with_variant_env_and_build_depends_hooks(ld):
    p = ld.load("c-auto")
    for base in ("env", "build-env"):
        for prefix in ("", "common-", "default-", "cross-", "common-cross-", "default-cross-"):
            key = f"native-{prefix}{base}" if prefix else f"native-{base}"
            assert key in p.hooks, f"Missing hook: {key}"
            assert p.hooks[key] == {}


def test_with_variant_build_depends_and_patches(ld):
    p = ld.load("c-auto")
    for base in ("build-depends", "patches"):
        for prefix in ("", "common-", "default-", "cross-", "common-cross-", "default-cross-"):
            key = f"native-{prefix}{base}" if prefix else f"native-{base}"
            assert key in p.hooks, f"Missing hook: {key}"
            assert p.hooks[key] == []


def test_with_variant_does_not_override_explicit_hooks(ld):
    p = ld.load("c-auto")
    assert p.hooks["native-vcs"] == ["none"]
    assert p.hooks["config"] == ["./configure --prefix=$PREFIX"]
    assert p.hooks["build"] == ["make -j$JOBS"]


def test_with_variant_resolve_native_returns_empty(ld):
    p = ld.load("c-auto")
    r = ld.resolve_hook(p, "native", "config")
    assert r is not None
    assert r == []
    r = ld.resolve_hook(p, "native", "build")
    assert r == []
    r = ld.resolve_hook(p, "native", "install")
    assert r == []


def test_with_variant_resolve_auto_falls_to_base(ld):
    p = ld.load("c-auto")
    r = ld.resolve_hook(p, "auto", "build-depends")
    assert r is not None
    assert "os@-dpkg" in r


# -----------------------------------------------------------------------
# All fixture files parse
# -----------------------------------------------------------------------

def test_all_fixtures_parse(ld):
    yaml_files = list(PLUGIN_DIR.glob("*.yaml"))
    assert len(yaml_files) >= 9
    for pf in yaml_files:
        p = ld.load(pf.stem)
        assert p.name == pf.stem
