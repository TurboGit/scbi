"""Start-up settings (scbi/setup.py)."""

from pathlib import Path

from scbi import setup


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


def test_distribution_package_aliases_match_debian():
    plugins = Path(__file__).resolve().parents[2] / "scripts.d"

    def aliases(dist):
        lines = (plugins / f".pkgs-{dist}").read_text().splitlines()
        names = [line.split()[0] for line in lines if line.startswith("os@-")]
        assert len(names) == len(set(names)), f"duplicate aliases in {dist}"
        return set(names)

    debian = aliases("deb")
    for dist in ("fed", "ubt", "cos", "rhl", "mingw"):
        assert aliases(dist) == debian, dist
