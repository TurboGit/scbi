from pathlib import Path
import pytest

from src.scbi.build_env import BuildEnv


def test_defaults():
    be = BuildEnv(module="c-gmp")
    assert be.module == "c-gmp"
    assert be.variant == "default"
    assert be.scbi_target
    assert be.scbi_jobs > 0
    assert be.scbi_bdir == Path.cwd() / ".scbi-build"


def test_tvdv():
    be = BuildEnv(module="c-gmp", variant="release")
    assert "release" in be.tvdv
    assert be.scbi_target in be.tvdv


def test_tvdv_dir():
    be = BuildEnv(module="c-gmp", variant="release", scbi_bdir=Path("/tmp/build"))
    assert str(be.tvdv_dir) == f"/tmp/build/c-gmp/{be.tvdv}"


def test_subdirs():
    be = BuildEnv(module="c-gmp", variant="default", scbi_bdir=Path("/tmp/b"))
    assert be.module_root == Path("/tmp/b/c-gmp")
    assert "src" in str(be.src_dir)
    assert "build" in str(be.build_dir)
    assert "install" in str(be.install_dir)
    assert "logs" in str(be.logs_dir)


def test_ensure_dirs(tmp_path):
    be = BuildEnv(module="c-test", scbi_bdir=tmp_path)
    be.ensure_dirs()
    assert be.tvdv_dir.exists()
    assert be.logs_dir.exists()


def test_substitute():
    be = BuildEnv(
        module="c-test",
        variant="debug",
        scbi_bdir=Path("/b"),
        scbi_prefix=Path("/p"),
        scbi_target="x86_64-linux-gnu",
    )
    result = be.substitute("./configure --prefix=$PREFIX --host=$TARGET")
    assert result == "./configure --prefix=/p --host=x86_64-linux-gnu"


def test_substitute_joins():
    be = BuildEnv(
        module="c-test",
        scbi_bdir=Path("/b"),
        scbi_jobs=4,
    )
    result = be.substitute("make -j$JOBS")
    assert result == "make -j4"


def test_substitute_variant():
    be = BuildEnv(module="c-test", variant="release")
    result = be.substitute("echo $VARIANT")
    assert result == "echo release"


def test_is_cross_default():
    be = BuildEnv(module="c-test")
    assert not be.is_cross


def test_is_cross_when_host_differs():
    be = BuildEnv(module="c-test", scbi_host="x86_64-linux-gnu", scbi_target="aarch64-linux-gnu")
    assert be.is_cross


def test_is_cross_same_host_target():
    be = BuildEnv(module="c-test", scbi_host="x86_64-linux-gnu", scbi_target="x86_64-linux-gnu")
    assert not be.is_cross


def test_is_enabled_not_set():
    be = BuildEnv(module="c-test")
    assert not be.is_enabled("some-feature")


def test_is_enabled_set():
    be = BuildEnv(module="c-test", scbi_enabled_features={"some_feature": "true"})
    assert be.is_enabled("some-feature")


def test_is_enabled_set_with_underscore():
    be = BuildEnv(module="c-test", scbi_enabled_features={"some_feature": "true"})
    assert be.is_enabled("some_feature")


def test_is_enabled_not_true():
    be = BuildEnv(module="c-test", scbi_enabled_features={"some_feature": "false"})
    assert not be.is_enabled("some-feature")


def test_has_variant():
    be = BuildEnv(module="c-test")
    assert be.has_variant("release.debug", "release")
    assert be.has_variant("release.debug", "debug")
    assert not be.has_variant("release.debug", "clang")


def test_system_compiler():
    be = BuildEnv(module="c-test")
    env = be.system_compiler()
    assert env["PATH"] == "/usr/local/bin:/usr/bin:/bin"
    assert env["C_INCLUDE_PATH"] == ""
    assert env["LD_LIBRARY_PATH"] == ""


def test_get_version_number_basic():
    assert BuildEnv.get_version_number("6.2.1") != "0"


def test_get_version_number_invalid():
    assert BuildEnv.get_version_number("some-branch-name") == "0"


def test_get_version_number_with_underscore():
    v = BuildEnv.get_version_number("1_2_3")
    assert v != "0"


def test_get_version_number_trailing_dot():
    assert BuildEnv.get_version_number("1.2.") == "0"
