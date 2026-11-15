"""Start-up settings (scbi/setup.py)."""

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
