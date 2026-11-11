import os

import pytest

from scbi.bashenv import BashEvalError, ShellVars, source_files
from scbi.envfile import EnvNotFound, find_env_file, load_module_env

BASE_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C"}


def test_source_files_variables_and_functions(tmp_path):
    f = tmp_path / "env"
    f.write_text(
        "A=1\nexport B=${B:-2}\nC=$A$B\n"
        "function module-final-step()\n{\n    echo final $1\n}\n"
    )
    res = source_files([f], ShellVars({"B": "x"}, set()), base_env=BASE_ENV)
    assert res.values["A"] == "1"
    assert res.values["B"] == "x" and "B" in res.exported
    assert res.values["C"] == "1x"
    assert "A" not in res.exported
    assert "module-final-step ()" in res.functions["module-final-step"]


def test_source_files_functions_round_trip(tmp_path):
    f = tmp_path / "env"
    f.write_text("function hello()\n{\n    echo hi\n}\n")
    res = source_files([f], ShellVars(), base_env=BASE_ENV)
    g = tmp_path / "env2"
    g.write_text("OUT=$(hello)\n")
    assert source_files([g], res, base_env=BASE_ENV).values["OUT"] == "hi"


def test_source_files_exit(tmp_path):
    f = tmp_path / "env"
    f.write_text("echo boom; exit 3\n")
    with pytest.raises(BashEvalError) as e:
        source_files([f], ShellVars(), base_env=BASE_ENV)
    assert e.value.returncode == 3 and "boom" in e.value.output


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


def test_load_module_env(tmp_path):
    (tmp_path / ".env-x").write_text("SCBI_PLAN=${SCBI_PLAN:-default}\nSEEN=$SCBI_ENV_DIR\n")
    res = load_module_env("x", ShellVars(), tmp_path, tmp_path, tmp_path, BASE_ENV)
    assert res.values["SCBI_PLAN"] == "default"
    assert res.values["SEEN"] == str(tmp_path)
    with pytest.raises(EnvNotFound, match="build environment .env-nope not found"):
        load_module_env("nope", ShellVars(), tmp_path, tmp_path, tmp_path, BASE_ENV)
    #  missing default environment is fine
    assert load_module_env("", ShellVars({"K": "v"}), tmp_path / "x", tmp_path / "x", tmp_path / "x", BASE_ENV).values == {"K": "v"}


@pytest.mark.oracle
def test_setup_runtime_files_oracle(oracle, repo_root, tmp_path):
    """Variables set by 1_setup (reference and testsuite versions) and .env."""
    files = [
        repo_root / "scripts.d" / "1_setup",
        repo_root / "tests" / "scripts.d" / "1_setup",
        repo_root / "scripts.d" / ".env",
    ]
    names = [
        "SCBI_ROOT", "SCBI_BDIR", "SCBI_PREFIX", "SCBI_ARCHIVES", "SCBI_PATCH",
        "SCBI_LOGS", "SCBI_GIT_REPO", "SCBI_SVN_REPO", "SCBI_HG_REPO", "SCBI_PLAN",
        "SCBI_CLANG_VERSION", "SCBI_GTK_VERSION",
    ]
    for f in files:
        for seed in ({}, {"SCBI_ROOT": "/r", "SCBI_PLAN": "p"}):
            #  the oracle prelude already sourced 1_setup: start clean
            script = f"unset {' '.join(names)}\n"
            script += "".join(f"{k}={v}\n" for k, v in seed.items())
            script += f"cd {tmp_path}\nsource {f}\n"
            script += "".join(f'printf "%s\\x1f" "${{{n}}}"\n' for n in names)
            bash = oracle.call(script, {"SCBI_ROOT": ""} if "SCBI_ROOT" not in seed else {}).split("\x1f")[:-1]
            res = source_files([f], ShellVars(dict(seed), set()), cwd=tmp_path,
                               base_env={**BASE_ENV, "HOME": oracle.env()["HOME"]})
            assert [res.values.get(n, "") for n in names] == bash, (f, seed)
