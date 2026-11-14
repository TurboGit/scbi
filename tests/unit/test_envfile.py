"""Search of the environment files (scbi.envfile)."""

from scbi.envfile import find_env_file


def test_find_env_file_order(tmp_path):
    cwd = tmp_path / "a" / "cwd"
    home = tmp_path / "home"
    plugins = tmp_path / "plugins"
    for d in (cwd, home, plugins):
        d.mkdir(parents=True)
    assert find_env_file("", cwd, home, plugins) is None
    (plugins / ".env").write_text("")
    assert find_env_file("", cwd, home, plugins) == plugins / ".env"
    (home / ".scbi-env").write_text("")
    assert find_env_file("", cwd, home, plugins) == home / ".scbi-env"
    (cwd.parent / ".scbi-env").write_text("")
    assert find_env_file("", cwd, home, plugins) == cwd / ".." / ".scbi-env"
    (cwd / ".scbi-env").write_text("")
    assert find_env_file("", cwd, home, plugins) == cwd / ".scbi-env"
    (plugins / ".env-pkg").write_text("")
    assert find_env_file("pkg", cwd, home, plugins) == plugins / ".env-pkg"
