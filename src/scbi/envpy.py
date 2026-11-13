"""Environment files of the Python driver: ``.env.py`` / ``.env-<name>.py``.

An environment file is Python code, executed once when the driver starts.
It is searched, in order, as (``<ename>``: ``env`` or ``env-<name>`` for
``--env=<name>``):

    $PWD/.scbi-<ename>.py
    $PWD/../.scbi-<ename>.py
    $HOME/.scbi-<ename>.py
    $SCBI_PLUGINS/.<ename>.py

What it defines, all optional:

- settings: module-level variables in upper case holding a string, e.g.
  ``SCBI_PLAN = getvar("SCBI_PLAN", "default")`` (``getvar(name,
  default)``: the driver variable, or ``default`` when empty, as
  ``${NAME:-default}``); they become exported driver variables, given to
  the hooks;
- ``PASSTHROUGH = ["CC", ...]``: variables of the user's environment
  given to the hooks besides the base ones (see steps.hookenv);
- ``define_var(env, action, name, value)``: called for each environment
  action (ADD, SET, PREPEND...); ``env.apply(action, name, value)`` does
  the default action, ``env.get(name)`` reads a variable;
- ``rewrite_vcs(record)`` / ``rewrite_archive(record)``: the fields of a
  vcs / archive hook (list of strings: proxy, options, protocol, url,
  [file,] dir), returns the fields to use;
- ``proxy(name, env)``: the proxy ``name`` of a vcs/archive record,
  ``env`` the environment (dict) of the VCS or download command to change;
- ``module_final_step(ctx)``: called after each module (see
  :class:`scbi.steps.final.FinalStep` for ``ctx``).

``SCBI_ENV_DIR`` is set to the directory of the file before it runs.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scbi.envfile import env_file_name, find_env_file

HOOKS = ("define_var", "rewrite_vcs", "rewrite_archive", "proxy", "module_final_step")
_SETTING = re.compile(r"^[A-Z][A-Z0-9_]*$")


class EnvFileError(Exception):
    """An environment file which cannot be used (message for the user)."""


@dataclass
class EnvFile:
    path: Path | None = None
    settings: dict[str, str] = field(default_factory=dict)
    passthrough: tuple[str, ...] = ()
    hooks: dict[str, Callable] = field(default_factory=dict)

    def hook(self, name: str) -> Callable | None:
        return self.hooks.get(name)


def find(name: str, cwd: Path, home: Path, plugins_dir: Path) -> Path | None:
    ename = env_file_name(name)
    for candidate in (
        cwd / f".scbi-{ename}.py",
        cwd / ".." / f".scbi-{ename}.py",
        home / f".scbi-{ename}.py",
        plugins_dir / f".{ename}.py",
    ):
        if candidate.is_file():
            return candidate
    return None


def load(name: str, cwd: Path, home: Path, plugins_dir: Path, getvar: Callable[[str], str]) -> EnvFile:
    """Find and run the environment file ``name`` ("" for the default one).

    A missing default environment is not an error; a missing named one is.
    A Bash environment file without a Python version is an error: it is
    converted once with ``python3 -m scbi.envconvert``.
    """
    path = find(name, cwd, home, plugins_dir)
    if path is None:
        bash = find_env_file(name, cwd, home, plugins_dir)
        if bash is not None:
            raise EnvFileError(f"build environment {bash} is a Bash file, convert it with: "
                               f"python3 -m scbi.envconvert {bash}")
        if name:
            raise EnvFileError(f"build environment .{env_file_name(name)} not found")
        return EnvFile()
    return run(path, getvar)


def run(path: Path, getvar: Callable[[str], str]) -> EnvFile:
    """Execute the environment file ``path``."""
    env_dir = str(path.parent)

    def _getvar(var: str, default: str = "") -> str:
        if var == "SCBI_ENV_DIR":
            return env_dir
        return getvar(var) or default

    namespace: dict = {"__file__": str(path), "__name__": f"scbi_env_{path.stem}", "getvar": _getvar,
                       "SCBI_ENV_DIR": env_dir}
    try:
        code = compile(path.read_text(), str(path), "exec")
        exec(code, namespace)  # noqa: S102 - the user's configuration file
    except Exception as e:  # noqa: BLE001 - reported to the user
        raise EnvFileError(f"{path}: {type(e).__name__}: {e}") from None
    env = EnvFile(path)
    for key, value in namespace.items():
        if key in HOOKS and callable(value):
            env.hooks[key] = value
        elif key == "PASSTHROUGH":
            if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
                raise EnvFileError(f"{path}: PASSTHROUGH must be a list of variable names")
            env.passthrough = tuple(value)
        elif _SETTING.match(key) and isinstance(value, str):
            #  SCBI_ENV_DIR is set by the driver (unless the file changes it)
            if key == "SCBI_ENV_DIR" and value == env_dir:
                continue
            env.settings[key] = value
    return env
