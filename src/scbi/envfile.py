"""Search of the environment files (port of ``load-module-env``): the
driver reads the YAML ones (scbi.envyaml, suffix ``.yaml``) and reports a
Bash or Python file found without a YAML version.

For the default environment the name is ``env``, for ``--env=<name>`` it
is ``env-<name>``. It is searched, in order, as:

    $PWD/.scbi-<ename>
    $PWD/../.scbi-<ename>
    $HOME/.scbi-<ename>
    $SCBI_PLUGINS/.<ename>
"""

from __future__ import annotations

from pathlib import Path


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
