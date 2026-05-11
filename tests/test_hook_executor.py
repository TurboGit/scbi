from pathlib import Path
import pytest

from src.scbi.build_env import BuildEnv
from src.scbi.hook_executor import (
    HookExecutor,
    apply_env_operation,
    merge_env_dict,
)


def test_apply_add_to_var():
    env = {"PATH": "/usr/bin"}
    apply_env_operation(env, "add-to-var", "PATH", "/opt/bin")
    assert env["PATH"] == "/opt/bin:/usr/bin"


def test_apply_add_to_var_duplicate():
    env = {"PATH": "/opt/bin:/usr/bin"}
    apply_env_operation(env, "add-to-var", "PATH", "/opt/bin")
    assert env["PATH"] == "/opt/bin:/usr/bin"


def test_apply_set_var():
    env = {"OLD": "x"}
    apply_env_operation(env, "set-var", "NEW", "value")
    assert env["NEW"] == "value"


def test_apply_unset_var():
    env = {"TEMP": "value"}
    apply_env_operation(env, "unset-var", "TEMP", None)
    assert "TEMP" not in env


def test_apply_prepend():
    env = {"PATH": "/usr/bin"}
    apply_env_operation(env, "prepend-to-var", "PATH", "/opt/bin")
    assert env["PATH"] == "/opt/bin:/usr/bin"


def test_apply_append():
    env = {"PATH": "/usr/bin"}
    apply_env_operation(env, "append-to-var", "PATH", "/opt/bin")
    assert env["PATH"] == "/usr/bin:/opt/bin"


def test_apply_remove():
    env = {"PATH": "/a:/b:/c"}
    apply_env_operation(env, "remove-from-var", "PATH", "/b")
    assert env["PATH"] == "/a:/c"


def test_merge_env_dict():
    target = {"PATH": "/usr/bin"}
    source = {
        "add-to-var": ["PATH", "/opt/bin"],
        "set-var": ["CC", "gcc"],
    }
    merge_env_dict(target, source)
    assert target["PATH"] == "/opt/bin:/usr/bin"
    assert target["CC"] == "gcc"


def test_accumulate_env():
    be = BuildEnv(module="c-test", scbi_bdir=Path("/tmp/b"), scbi_prefix=Path("/p"))
    executor = HookExecutor(be)

    env_dict = {
        "add-to-var": ["PATH", "/opt/bin"],
        "set-var": ["CC", "gcc"],
    }
    executor.accumulate_env(env_dict)
    assert "/opt/bin" in executor.env.get("PATH", "")
    assert executor.env.get("CC") == "gcc"


def test_accumulate_env_substitution():
    be = BuildEnv(module="c-test", scbi_prefix=Path("/opt/pkg"))
    executor = HookExecutor(be)

    env_dict = {
        "add-to-var": ["PATH", "$PREFIX/bin"],
    }
    executor.accumulate_env(env_dict)
    assert "/opt/pkg/bin" in executor.env.get("PATH", "")


def test_run_simple_command(tmp_path):
    be = BuildEnv(module="c-test", scbi_bdir=tmp_path)
    executor = HookExecutor(be)

    code = executor.run_commands(["echo hello > " + str(tmp_path / "out.txt")])
    assert code == 0
    assert (tmp_path / "out.txt").read_text().strip() == "hello"
