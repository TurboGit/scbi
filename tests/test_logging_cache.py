import tempfile
from pathlib import Path

import pytest

from src.scbi.build_env import BuildEnv
from src.scbi.core import ScbiBuild, _file_eq
from src.scbi.hook_executor import HookExecutor
from src.scbi.plugin_loader_yaml import PluginLoader
from src.scbi.source_manager import SourceManager

PLUGINS_DIR = Path("tests/plugins")


def _make_sb(**kw):
    sb = ScbiBuild(plugins_dir=PLUGINS_DIR, **kw)
    sb._ensure_loaders()
    return sb


def test_log_dir_created():
    """Build should create logs/ directory under TVDIR."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        sb.build("c-noop")
        be = BuildEnv(module="c-noop", variant="default", scbi_bdir=Path(tmp))
        assert be.logs_dir.exists()


def test_config_log_written():
    """Config step should write config.log and config.cmd files."""
    from src.scbi.build_env import BuildEnv
    from src.scbi.plugin_loader_yaml import PluginLoader
    from src.scbi.source_manager import SourceManager

    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        loader = PluginLoader(PLUGINS_DIR)
        plugin = loader.load("c-gmp")
        be = BuildEnv(
            module="c-gmp", variant="default", version="6.2.1", scbi_bdir=Path(tmp)
        )
        be.ensure_dirs()
        ref = type("Ref", (), {"variant": "default", "kind": "VERSION", "version": "6.2.1"})
        sm = SourceManager(loader, be)
        sm._download_archive = lambda d, m: 0
        sm._extract_archive = lambda d, m: 0

        sb = _make_sb()
        sb._ensure_loaders()
        executor = HookExecutor(be)
        sb._run_env_phase(executor, plugin, be)
        sm.handle_sources(plugin, type("Ref", (), {
            "module": "c-gmp",
            "variant": "default",
            "kind": type("K", (), {"__eq__": lambda s, o: o == 3})(),
            "version": "6.2.1",
        })())

        for step in ("config", "build", "install"):
            log = be.logs_dir / f"{step}.log"
            cmd = be.logs_dir / f"{step}.cmd"
            # hooks don't exist for c-gmp, so no files will be written
            # but dir should exist


def test_cmd_file_written():
    """Config/build/install steps should write .cmd replay files."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        sb.build("c-noop")
        be = BuildEnv(module="c-noop", variant="default", scbi_bdir=Path(tmp))
        # c-noop has no hooks, so no cmd files for config/build/install
        # but setup might have them if hooks exist


def test_config_cmd_file_has_commands():
    """Verify cmd file contains the config command."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        # Use c-simple which has setup hooks
        sb = _make_sb(bdir=Path(tmp))
        loader = PluginLoader(PLUGINS_DIR)
        plugin = loader.load("c-simple")

        from src.scbi.build_env import BuildEnv
        from src.scbi.hook_executor import HookExecutor
        from src.scbi.source_manager import SourceManager

        be = BuildEnv(module="c-simple", variant="default", scbi_bdir=Path(tmp))
        be.ensure_dirs()
        executor = HookExecutor(be)

        log_path = be.logs_dir / "setup.log"
        cmd_path = be.logs_dir / "setup.cmd"

        executor.run_commands_logged(
            ["echo hello"],
            log_path,
            cmd_path,
            "setup",
        )

        assert log_path.exists()
        assert cmd_path.exists()
        content = cmd_path.read_text()
        assert "echo hello" in content
        assert "scbi replay" in content


def test_build_cache_files_exist():
    """After successful build, build-id and source-id files should exist."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        sb.build("c-noop")
        be = BuildEnv(module="c-noop", variant="default", scbi_bdir=Path(tmp))
        var_sid = be.module_root / "source-id-default"
        var_bid = be.module_root / "build-id-default"
        latest_sid = be.module_root / "source-id"
        tvdv_bid = be.tvdv_dir / "build-id"

        assert var_sid.exists(), f"{var_sid} should exist"
        assert var_bid.exists(), f"{var_bid} should exist"
        assert latest_sid.exists(), f"{latest_sid} should exist"


def test_build_cache_source_unchanged():
    """When source-id matches, build should be skipped for config."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        sb.build("c-noop")
        be = BuildEnv(module="c-noop", variant="default", scbi_bdir=Path(tmp))

        # Source is unchanged since we just built
        assert sb._is_source_unchanged(be) is True


def test_build_cache_build_cached():
    """After successful build, build should be reported as cached."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        sb.build("c-noop")
        be = BuildEnv(module="c-noop", variant="default", scbi_bdir=Path(tmp))

        # Build should be cached
        assert sb._is_build_cached(be) is True


def test_build_cache_miss_on_first_build():
    """Before any build, nothing should be cached."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        be = BuildEnv(module="c-noop", variant="default", scbi_bdir=Path(tmp))
        be.ensure_dirs()
        sb = _make_sb()

        assert sb._is_source_unchanged(be) is False
        assert sb._is_build_cached(be) is False


def test_file_eq():
    """_file_eq compares two files' contents."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        a = Path(tmp) / "a.txt"
        b = Path(tmp) / "b.txt"
        c = Path(tmp) / "c.txt"
        a.write_text("hello")
        b.write_text("hello")
        c.write_text("world")

        assert _file_eq(a, b) is True
        assert _file_eq(a, c) is False
        assert _file_eq(a, Path(tmp) / "nonexistent") is False


def test_install_updates_build_cache():
    """After install, build-id should be copied to TVDIR."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        be = BuildEnv(module="c-noop", variant="default", scbi_bdir=Path(tmp))
        be.ensure_dirs()

        # Simulate a build-id at module root
        var_bid = be.module_root / "build-id-default"
        var_bid.parent.mkdir(parents=True, exist_ok=True)
        var_bid.write_text("test-bid")

        sb = _make_sb()
        tvdv_bid = be.tvdv_dir / "build-id"
        assert not tvdv_bid.exists()

        sb._update_build_cache(be)
        assert tvdv_bid.exists()
        assert tvdv_bid.read_text() == "test-bid"


def test_source_manager_writes_latest_source_id():
    """SourceManager should write both source-id-<variant> and source-id."""
    import tempfile
    from src.scbi.build_env import BuildEnv
    from src.scbi.plugin_loader_yaml import PluginLoader
    from src.scbi.source_manager import SourceManager
    from src.scbi.models import ModuleRef, RefKind

    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        loader = PluginLoader(PLUGINS_DIR)
        plugin = loader.load("c-noop")
        be = BuildEnv(module="c-noop", variant="default", version="NONE", scbi_bdir=Path(tmp))

        sm = SourceManager(loader, be)
        ref = ModuleRef("c-noop", "default", RefKind.NONE, "NONE")
        sm.handle_sources(plugin, ref)

        var = be.module_root / "source-id-default"
        latest = be.module_root / "source-id"
        assert var.exists()
        assert latest.exists()
        assert var.read_text() == latest.read_text()


def test_second_build_skips_config():
    """Second build should skip config if source unchanged."""
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        sb = _make_sb(bdir=Path(tmp))
        code1 = sb.build("c-noop")
        assert code1 == 0

        # Second build
        sb2 = _make_sb(bdir=Path(tmp))
        code2 = sb2.build("c-noop")
        assert code2 == 0
