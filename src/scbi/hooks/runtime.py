"""The Bash runtime available to the hooks.

Hooks are shell code calling runtime helpers (get-config-options,
gprbuild-project, add-to-var...). The runtime is the set of files
``$SCBI_PLUGINS/[0-9]*`` (and ``_os_<os>``), which a user or the testsuite
may override (e.g. ``1_setup``). It is evaluated once per driver run: its
functions and settings are then given to every hook shell.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scbi.bashenv import ShellVars, source_files

COMPAT = Path(__file__).with_name("compat.sh")


@dataclass
class Runtime:
    #  Functions of the runtime files and the variables they set
    vars: ShellVars
    #  Driver functions needed by the runtime (compat.sh)
    compat: str

    @property
    def functions(self) -> dict[str, str]:
        return self.vars.functions


def runtime_files(plugins_dir: Path, os_module: str = "") -> list[Path]:
    plugins_dir = Path(plugins_dir).resolve()
    files = sorted(p for p in Path(plugins_dir).glob("[0-9]*") if p.is_file() and not p.name.endswith("~"))
    if os_module:
        osf = Path(plugins_dir) / f"_os_{os_module}"
        if osf.is_file():
            files.append(osf)
    return files


def load_runtime(
    plugins_dir: Path,
    svars: ShellVars,
    cwd: Path | None = None,
    base_env: dict[str, str] | None = None,
    os_module: str = "",
) -> Runtime:
    """Source the runtime files (with the driver variables ``svars``)."""
    compat = COMPAT.read_text()
    res = source_files(runtime_files(plugins_dir, os_module), svars, cwd=cwd,
                       base_env=base_env, prelude=compat)
    return Runtime(res, compat)
