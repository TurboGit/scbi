"""Environment files (port of ``load-module-env`` in the scbi driver).

An environment file is Bash code setting SCBI variables. For the default
environment the name is ``env``, for ``--env=<name>`` it is ``env-<name>``.
It is searched, in order, as:

    $PWD/.scbi-<ename>
    $PWD/../.scbi-<ename>
    $HOME/.scbi-<ename>
    $SCBI_PLUGINS/.<ename>
"""

from __future__ import annotations

from pathlib import Path

from scbi.bashenv import ShellVars, source_files


class EnvNotFound(Exception):
    pass


def env_file_name(name: str = "") -> str:
    return "env" + (f"-{name}" if name else "")


def find_env_file(name: str, cwd: Path, home: Path, plugins_dir: Path) -> Path | None:
    ename = env_file_name(name)
    for candidate in (
        cwd / f".scbi-{ename}",
        cwd / ".." / f".scbi-{ename}",
        home / f".scbi-{ename}",
        plugins_dir / f".{ename}",
    ):
        if candidate.is_file():
            return candidate
    return None


def load_module_env(
    name: str,
    svars: ShellVars,
    cwd: Path,
    home: Path,
    plugins_dir: Path,
    base_env: dict[str, str] | None = None,
) -> ShellVars:
    """Load environment ``name`` ("" for the default one).

    Returns the new variables (``SCBI_ENV_DIR`` set to the file directory).
    A missing default environment is not an error; a missing named one
    raises EnvNotFound with the Bash driver message.
    """
    path = find_env_file(name, cwd, home, plugins_dir)
    if path is None:
        if name:
            raise EnvNotFound(f"build environment .{env_file_name(name)} not found")
        return svars.copy()

    seeded = svars.copy()
    #  SCBI_ENV_DIR=$(dirname $ENV), set before sourcing
    seeded.set("SCBI_ENV_DIR", str(path.parent), export=True)
    return source_files([path], seeded, cwd=cwd, base_env=base_env)
