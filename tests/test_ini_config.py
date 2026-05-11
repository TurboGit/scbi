from pathlib import Path
from src.scbi.ini_config import IniConfig, load_module_env, parse_env_file


def test_ini_load_simple(tmp_path):
    ini = tmp_path / ".scbi"
    ini.write_text(
        "[build]\n"
        "jobs=4\n"
        "prefix=/opt/test\n"
    )
    config = IniConfig()
    config._load_file(ini)
    assert config._db["build.jobs"] == "4"
    assert config._db["build.prefix"] == "/opt/test"


def test_ini_common_section(tmp_path):
    ini = tmp_path / ".scbi"
    ini.write_text(
        "[common]\n"
        "jobs=2\n"
    )
    config = IniConfig()
    config._load_file(ini)
    assert config._db["common.jobs"] == "2"
    vals = config.apply_values("build")
    assert vals.get("SCBI_JOBS") == "2"


def test_ini_multivalue_keys(tmp_path):
    ini = tmp_path / ".scbi"
    ini.write_text(
        "[default]\n"
        "enable=feature1 feature2\n"
        "modules=mod-a mod-b\n"
    )
    config = IniConfig()
    config._load_file(ini)
    assert "feature1" in config._db.get("default.enable", "")
    assert "feature2" in config._db.get("default.enable", "")
    vals = config.apply_values("default")
    assert vals.get("SCBI_feature1_SET") == "true"
    assert vals.get("SCBI_feature2_SET") == "true"


def test_ini_step_options(tmp_path):
    ini = tmp_path / ".scbi"
    ini.write_text(
        "[test]\n"
        "quiet=yes\n"
        "force=yes\n"
    )
    config = IniConfig()
    config._load_file(ini)
    vals = config.apply_values("test")
    assert vals.get("DO_QUIET") == "yes"
    assert vals.get("DO_FORCE") == "yes"


def test_ini_bool_options(tmp_path):
    ini = tmp_path / ".scbi"
    ini.write_text(
        "[test]\n"
        "safe=yes\n"
        "no-patch=yes\n"
    )
    config = IniConfig()
    config._load_file(ini)
    vals = config.apply_values("test")
    opts = vals.get("SCBI_INI_OPTIONS", [])
    assert "--safe" in opts
    assert "--no-patch" in opts


def test_ini_controlled_vars(tmp_path):
    ini = tmp_path / ".scbi"
    ini.write_text(
        "[target]\n"
        "build-dir=/custom/build\n"
        "prefix=/custom/prefix\n"
        "target=aarch64-linux-gnu\n"
    )
    config = IniConfig()
    config._load_file(ini)
    vals = config.apply_values("target")
    assert vals["SCBI_BDIR"] == "/custom/build"
    assert vals["SCBI_PREFIX"] == "/custom/prefix"
    assert vals["SCBI_TARGET"] == "aarch64-linux-gnu"


def test_ini_free_vars(tmp_path):
    ini = tmp_path / ".scbi"
    ini.write_text(
        "[custom]\n"
        "my-var=hello\n"
        "another_val=world\n"
    )
    config = IniConfig()
    config._load_file(ini)
    vals = config.apply_values("custom")
    assert vals.get("my_var") == "hello"
    assert vals.get("another_val") == "world"


def test_ini_load_order(tmp_path):
    home_ini = tmp_path / "home" / ".scbi"
    home_ini.parent.mkdir(parents=True)
    home_ini.write_text("[base]\nquiet=yes\n")

    cwd_ini = tmp_path / "cwd" / ".scbi"
    cwd_ini.parent.mkdir(parents=True)
    cwd_ini.write_text("[base]\njobs=8\n")

    extra_ini = tmp_path / "extra" / ".scbi"
    extra_ini.parent.mkdir(parents=True)
    extra_ini.write_text("[base]\njobs=16\n")

    import os
    orig_home = os.environ.get("HOME")
    orig_cwd = str(Path.cwd())
    try:
        os.environ["HOME"] = str(home_ini.parent)
        os.chdir(str(cwd_ini.parent))
        config = IniConfig()
        config.load_files(str(extra_ini))
        vals = config.apply_values("base")
        assert vals.get("SCBI_JOBS") == "16"
    finally:
        if orig_home:
            os.environ["HOME"] = orig_home
        os.chdir(orig_cwd)


def test_parse_env_file_simple(tmp_path):
    env_file = tmp_path / ".scbi-env-test"
    env_file.write_text(
        'export SCBI_ROOT=$PWD\n'
        'SCBI_BDIR=$SCBI_ROOT/builds\n'
        'SCBI_PREFIX=/usr/local\n'
    )
    env = parse_env_file(env_file)
    assert env.get("SCBI_ROOT") == "$PWD"
    assert env.get("SCBI_BDIR") == "$SCBI_ROOT/builds"
    assert env.get("SCBI_PREFIX") == "/usr/local"


def test_store_basic(tmp_path):
    from src.scbi.store import Store
    store = Store(tmp_path / ".store")
    store.set_key("foo", "bar")
    val, found = store.get_key("foo")
    assert found is True
    assert val == "bar"

    val, found = store.get_key("nonexistent")
    assert found is False
    assert val is None


def test_store_overwrite(tmp_path):
    from src.scbi.store import Store
    store = Store(tmp_path / ".store")
    store.set_key("key1", "val1")
    store.set_key("key2", "val2")
    store.set_key("key1", "updated")
    val, found = store.get_key("key1")
    assert val == "updated"


def test_store_list_keys(tmp_path):
    from src.scbi.store import Store
    store = Store(tmp_path / ".store")
    store.set_key("a", "1")
    store.set_key("b", "2")
    keys = store.list_keys()
    assert "a" in keys
    assert "b" in keys


def test_load_module_env_not_found():
    result = load_module_env(None, Path("/nonexistent"))
    assert result == (None, None)
