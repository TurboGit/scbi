"""Start-up settings (scbi/setup.py) compared with the top-level code of
the Bash runtime files (1_setup, 6_distpkg) sourced by the oracle."""

import shutil

import pytest

from oracle import REPO_ROOT, BashOracle
from scbi import setup


@pytest.fixture(scope="module")
def oracle(tmp_path_factory):
    return BashOracle(tmp_path_factory.mktemp("setup"))


ENVS = [
    {},
    {"SCBI_ROOT": ""},
    {"SCBI_BDIR": "/b/dir"},
    {"SCBI_ROOT": "/r", "SCBI_LOGS": "/l", "SCBI_HG_REPO": "/hg"},
    {"SCBI_ROOT": "", "SCBI_PREFIX": "/p", "SCBI_ARCHIVES": "/a", "SCBI_PATCH": ""},
]


@pytest.mark.oracle
@pytest.mark.parametrize("extra", ENVS)
def test_defaults_same_as_bash(oracle, extra):
    env = oracle.env(extra)
    names = [n for n, _ in setup.DEFAULTS]
    out = oracle.call("".join(f'printf "%s\\0" "${n}"\n' for n in names), extra)
    bash = dict(zip(names, out.split("\0")[:-1]))
    assert setup.defaults(lambda v: env.get(v, "")) == bash


def test_test_os_packages():
    env = {"SCBI_TESTSUITE": "yes", "SCBI_TEST_PKGS": "rsync=1 gcc=12.2"}
    assert setup.os_packages("test", lambda v: env.get(v, ""), "/") == ({"rsync": "1", "gcc": "12.2"}, {})
    #  outside of the testsuite: an unknown distribution
    assert setup.os_packages("test", lambda v: "", "/") == ({}, {})


def test_alias_files(tmp_path):
    (tmp_path / ".pkgs-xyz").write_text("os@-a   pa pb\n\n  os@-b pc  \n")
    (tmp_path / ".pkgs-xyz-extra").write_text("os@-a other\n")
    alias = {}
    setup._read_alias(tmp_path / ".pkgs-xyz", alias)
    assert alias == {"os@-a": "other", "os@-b": "pc"}


@pytest.mark.oracle
@pytest.mark.skipif(shutil.which("dpkg-query") is None or shutil.which("lsb_release") is None,
                    reason="needs a Debian-like host")
def test_packages_and_aliases_same_as_bash(oracle):
    bdir = oracle.var("", "SCBI_BDIR")
    env = {"SCBI_PLUGINS": str(REPO_ROOT / "scripts.d"), "SCBI_BDIR": bdir, "SCBI_IS_WINDOWS": "no"}
    os_name = oracle.var("", "SCBI_OS_NAME")
    if os_name not in ("deb", "ubt"):
        pytest.skip("not a Debian-like host")
    pkgs, alias = setup.os_packages(os_name, lambda v: env.get(v, ""), str(oracle.workdir))
    assert pkgs == oracle.assoc("", "SCBI_PKGS")
    assert alias == oracle.assoc("", "SCBI_ALIAS")
