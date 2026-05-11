from pathlib import Path
from unittest.mock import patch

from src.scbi.auto_variant import resolve_auto_variant, check_os_package
from src.scbi.plugin_loader_yaml import PluginLoader

PLUGINS = Path("tests/plugins")


def test_no_auto_variant_unchanged():
    loader = PluginLoader(PLUGINS)
    plugin = loader.load("c-noop")
    resolved, msg = resolve_auto_variant(loader, plugin, "default", PLUGINS)
    assert resolved == "default"
    assert msg is None


def test_auto_variant_no_native_depends():
    loader = PluginLoader(PLUGINS)
    plugin = loader.load("c-auto-no-deps")
    resolved, msg = resolve_auto_variant(loader, plugin, "auto", PLUGINS)
    assert resolved == "auto"
    assert msg is None


@patch("src.scbi.auto_variant.check_os_package")
def test_auto_variant_all_deps_found(mock_check):
    mock_check.return_value = (True, "1.0")
    loader = PluginLoader(PLUGINS)
    plugin = loader.load("c-auto")
    resolved, msg = resolve_auto_variant(loader, plugin, "auto", PLUGINS)
    assert resolved == "native"
    assert msg is not None
    assert "native" in str(msg)


@patch("src.scbi.auto_variant.check_os_package")
def test_auto_variant_all_deps_found_with_rest(mock_check):
    mock_check.return_value = (True, "1.0")
    loader = PluginLoader(PLUGINS)
    plugin = loader.load("c-auto")
    resolved, msg = resolve_auto_variant(loader, plugin, "auto.debug", PLUGINS)
    assert resolved == "native.debug"
    assert msg is not None


@patch("src.scbi.auto_variant.check_os_package")
def test_auto_variant_dep_not_found(mock_check):
    mock_check.return_value = (False, "0")
    loader = PluginLoader(PLUGINS)
    plugin = loader.load("c-auto")
    resolved, msg = resolve_auto_variant(loader, plugin, "auto", PLUGINS)
    assert resolved == "default"
    assert msg is not None
    assert "not found" in str(msg).lower()


@patch("src.scbi.auto_variant.check_os_package")
def test_auto_variant_dep_not_found_with_rest(mock_check):
    mock_check.return_value = (False, "0")
    loader = PluginLoader(PLUGINS)
    plugin = loader.load("c-auto")
    resolved, msg = resolve_auto_variant(loader, plugin, "auto.debug", PLUGINS)
    assert resolved == "debug"
    assert msg is not None


def test_check_os_package_returns_tuple():
    found, ver = check_os_package("os@-bash")
    assert isinstance(found, bool)
    assert isinstance(ver, str)


def test_auto_variant_with_build(tmp_path):
    from src.scbi.core import ScbiBuild
    sb = ScbiBuild(
        plugins_dir=PLUGINS,
        bdir=tmp_path,
    )
    code = sb.build("c-auto/auto")
    assert code == 0


def test_auto_variant_non_auto_unchanged(tmp_path):
    from src.scbi.core import ScbiBuild
    sb = ScbiBuild(
        plugins_dir=PLUGINS,
        bdir=tmp_path,
    )
    code = sb.build("c-noop")
    assert code == 0
