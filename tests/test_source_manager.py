import os
import tempfile
from pathlib import Path

import pytest

from src.scbi.build_env import BuildEnv
from src.scbi.models import ModuleRef, RefKind
from src.scbi.plugin_loader_yaml import PluginLoader
from src.scbi.source_manager import SourceManager, _parse_vcs_data, _parse_archive_data


PLUGINS_DIR = Path("tests/plugins")


@pytest.fixture
def build_dir():
    with tempfile.TemporaryDirectory(prefix="scbi-test-") as tmp:
        yield Path(tmp)


@pytest.fixture
def loader():
    return PluginLoader(PLUGINS_DIR)


def test_parse_vcs_data_full():
    data = _parse_vcs_data(["none", "no-recursive", "git", "https://example.com/repo.git", "subdir"])
    assert data["proxy"] == "none"
    assert data["options"] == "no-recursive"
    assert data["name"] == "git"
    assert data["url"] == "https://example.com/repo.git"
    assert data["dir"] == "subdir"
    assert data["kind"] == "git"


def test_parse_vcs_data_minimal():
    data = _parse_vcs_data(["none", "none", "mercurial", "https://example.com/hg"])
    assert data["proxy"] == "none"
    assert data["options"] == "none"
    assert data["name"] == "mercurial"
    assert data["url"] == "https://example.com/hg"
    assert data["dir"] == ""


def test_parse_archive_data_full():
    data = _parse_archive_data(["none", "", "curl", "https://example.com/dl", "foo-1.0.tar.xz"])
    assert data["proxy"] == "none"
    assert data["options"] == ""
    assert data["tool"] == "curl"
    assert data["url"] == "https://example.com/dl"
    assert data["filename"] == "foo-1.0.tar.xz"


def test_parse_archive_data_kind():
    data = _parse_archive_data(["none", "", "none", "", ""])
    assert data["kind"] == "none"


def test_source_manager_none_vcs(loader, build_dir):
    """Test source manager handles 'none' VCS correctly."""
    plugin = loader.load("c-noop")
    ref = ModuleRef.parse("c-noop")
    be = BuildEnv(module="c-noop", variant="default", version="NONE", scbi_bdir=build_dir)

    sm = SourceManager(loader, be)
    code = sm.handle_sources(plugin, ref)
    assert code == 0

    sid_path = be.module_root / f"source-id-{be.variant}"
    assert sid_path.exists()
    assert sid_path.read_text() == "none-NONE"


def test_source_manager_archive_parsing_gmp(loader):
    """Test source manager parsing for c-gmp archive hook."""
    plugin = loader.load("c-gmp")
    results = loader.resolve_all_hooks(plugin, "default", "archive")
    assert len(results) > 0
    data = _parse_archive_data(results[0])
    assert data["tool"] == "curl"
    assert "$VERSION" in data["filename"]
    assert "gmplib.org" in data["url"]


def test_source_manager_vcs_parsing_gmp(loader):
    """Test source manager parsing for c-gmp vcs hook."""
    plugin = loader.load("c-gmp")
    results = loader.resolve_all_hooks(plugin, "default", "vcs")
    assert len(results) > 0
    data = _parse_vcs_data(results[0])
    assert data["kind"] == "mercurial"
    assert "gmplib.org" in data["url"]


def test_source_manager_handle_none(loader, build_dir):
    """Test handle_none writes tracking files."""
    be = BuildEnv(module="c-noop", variant="default", version="NONE", scbi_bdir=build_dir)
    plugin = loader.load("c-noop")
    ref = ModuleRef.parse("c-noop")

    sm = SourceManager(loader, be)
    code = sm.handle_sources(plugin, ref)
    assert code == 0

    sid = be.module_root / "source-id-default"
    sref = be.module_root / "source-ref"
    bid = be.module_root / "build-id-default"
    assert sid.exists()
    assert sref.exists()
    assert bid.exists()
    assert sid.read_text() == "none-NONE"


def test_source_manager_native_variant(loader, build_dir):
    """Test native variant writes proper source-id."""
    be = BuildEnv(module="c-simple", variant="native", version="NONE", scbi_bdir=build_dir)
    plugin = loader.load("c-simple")
    ref = ModuleRef.parse("c-simple/native")

    sm = SourceManager(loader, be)
    code = sm.handle_sources(plugin, ref)
    assert code == 0

    sid = be.module_root / "source-id-native"
    sref = be.module_root / "source-ref"
    assert sid.exists()
    assert sid.read_text() == "native-NONE"
    assert sref.exists()
    assert "none native" in sref.read_text()


def test_source_manager_archive_skip_empty_tool(loader, build_dir):
    """When archive tool is 'none', skip download/extract."""
    be = BuildEnv(
        module="c-gmp", variant="default", version="6.2.1", scbi_bdir=build_dir
    )
    plugin = loader.load("c-gmp")
    ref = ModuleRef.parse("c-gmp:#6.2.1")

    sm = SourceManager(loader, be)
    sm._download_archive = lambda data, mod: 0
    sm._extract_archive = lambda data, mod: 0

    code = sm.handle_sources(plugin, ref)
    assert code == 0

    sid = be.module_root / "source-id-default"
    assert sid.exists()
    assert "archive-" in sid.read_text()


def test_source_manager_symlink_src_after_archive_extract(loader, build_dir):
    """After archive extraction, src symlink should point to archive-src."""
    be = BuildEnv(
        module="c-gmp", variant="default", version="6.2.1", scbi_bdir=build_dir
    )
    plugin = loader.load("c-gmp")
    ref = ModuleRef.parse("c-gmp:#6.2.1")

    sm = SourceManager(loader, be)
    sm._download_archive = lambda data, mod: 0
    # simulate extract by creating archive-src dir
    sm._extract_archive = lambda data, mod: (
        (be.module_root / "archive-src").mkdir(parents=True, exist_ok=True)
        or 0
    )

    sm.handle_sources(plugin, ref)

    src_link = be.module_root / "src"
    assert src_link.is_symlink()


def test_source_manager_archive_uses_version_subst(loader):
    """$VERSION should be substituted in archive filename."""
    plugin = loader.load("c-gmp")
    results = loader.resolve_all_hooks(plugin, "default", "archive")
    data = _parse_archive_data(results[0])
    assert "$VERSION" in data["filename"]
    # After substitution
    be = BuildEnv(module="c-gmp", variant="default", version="6.2.1")
    filename = be.substitute(data["filename"])
    assert "6.2.1" in filename
    assert "$VERSION" not in filename


def test_source_manager_git_vcs_returns_error_on_bad_url(loader, build_dir):
    """Cloning a non-existent git URL should return error code."""
    be = BuildEnv(module="c-simple", variant="default", version="NONE", scbi_bdir=build_dir)
    plugin = loader.load("c-simple")
    ref = ModuleRef.parse("c-simple")

    sm = SourceManager(loader, be)
    code = sm.handle_sources(plugin, ref)
    assert code != 0
