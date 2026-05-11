import tempfile
from pathlib import Path

from src.scbi.build_env import BuildEnv
from src.scbi.core import ScbiBuild
from src.scbi.models import ModuleRef, RefKind
from src.scbi.plugin_loader_yaml import PluginLoader

PLUGINS_DIR = Path("tests/plugins")


def _make_sb(**kw):
    sb = ScbiBuild(plugins_dir=PLUGINS_DIR, **kw)
    sb._ensure_loaders()
    return sb


def test_meta_module_has_modules():
    loader = PluginLoader(PLUGINS_DIR)
    plugin = loader.load("c-meta")
    assert "modules" in plugin.hooks
    assert plugin.hooks["modules"] == ["c-sub-a", "c-sub-b"]


def test_meta_module_has_aggregate():
    loader = PluginLoader(PLUGINS_DIR)
    plugin = loader.load("c-meta")
    assert "aggregate" in plugin.hooks


def test_meta_module_has_env():
    loader = PluginLoader(PLUGINS_DIR)
    plugin = loader.load("c-meta")
    assert "env" in plugin.hooks
    assert isinstance(plugin.hooks["env"], dict)


def test_get_modules_from_meta():
    sb = _make_sb()
    loader = sb.plugin_loader
    plugin = loader.load("c-meta")
    be = BuildEnv(module="c-meta", variant="default")
    modules = sb._get_modules(plugin, be)
    assert modules is not None
    assert modules == ["c-sub-a", "c-sub-b"]


def test_get_modules_from_normal_returns_none():
    sb = _make_sb()
    loader = sb.plugin_loader
    plugin = loader.load("c-simple")
    be = BuildEnv(module="c-simple", variant="default")
    modules = sb._get_modules(plugin, be)
    assert modules is None


def test_is_out_of_tree_default():
    sb = _make_sb()
    loader = sb.plugin_loader
    plugin = loader.load("c-simple")
    be = BuildEnv(module="c-simple", variant="default")
    oot = sb._is_out_of_tree(plugin, be)
    assert oot is True


def test_is_out_of_tree_gmp():
    sb = _make_sb()
    loader = sb.plugin_loader
    plugin = loader.load("c-gmp")
    be = BuildEnv(module="c-gmp", variant="default")
    oot = sb._is_out_of_tree(plugin, be)
    assert oot is False


def test_config_options_resolve():
    sb = _make_sb()
    loader = sb.plugin_loader
    plugin = loader.load("c-gmp")
    be = BuildEnv(
        module="c-gmp",
        variant="default",
        version="6.2.1",
        scbi_prefix=Path("/tmp/prefix"),
    )
    opts = sb._resolve_config_options(plugin, be)
    assert isinstance(opts, str)


def test_build_c_noop():
    """Verify c-noop builds cleanly through full pipeline."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        code = sb.build("c-noop")
        assert code == 0


def test_build_meta_module():
    """Meta-module should build its children."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        code = sb.build("c-meta")
        assert code == 0
        assert (Path(tmp) / "c-sub-a").exists()
        assert (Path(tmp) / "c-sub-b").exists()


def test_setup_step_no_hooks_creates_dirs():
    """Setup step creates build dir and processes out-of-tree."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        code = sb.build("c-noop")
        assert code == 0
        be = BuildEnv(
            module="c-noop", variant="default", scbi_bdir=Path(tmp)
        )
        assert be.build_dir.exists()


def test_handle_sources_with_ref_version():
    """source-id should reflect the version ref."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        loader = PluginLoader(PLUGINS_DIR)
        be = BuildEnv(
            module="c-gmp",
            variant="default",
            version="6.2.1",
            scbi_bdir=Path(tmp),
        )
        from src.scbi.source_manager import SourceManager
        plugin = loader.load("c-gmp")
        ref = ModuleRef.parse("c-gmp:#6.2.1")
        sm = SourceManager(loader, be)
        sm._download_archive = lambda d, m: 0
        sm._extract_archive = lambda d, m: 0
        code = sm.handle_sources(plugin, ref)
        assert code == 0
        sid = be.module_root / "source-id-default"
        assert sid.exists()
        assert "archive-6.2.1" in sid.read_text()
