"""Inputs collected from the repository, used by the unit tests."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PLUGIN_DIRS = [REPO_ROOT / "scripts.d", REPO_ROOT / "tests" / "scripts.d"]
#  Bash plug-ins, inputs of the converter (the former test plug-ins)
BASH_PLUGIN_DIRS = [REPO_ROOT / "tests" / "fixtures" / "bash"]


@cache
def plan_files() -> list[Path]:
    files: list[Path] = []
    for d in PLUGIN_DIRS:
        files += sorted(p for p in d.glob(".plan-*") if not p.name.endswith("~"))
    return files


@cache
def plugin_files() -> list[Path]:
    """Bash plug-in files (converter fixtures): not dot, backup or YAML
    files."""
    files: list[Path] = []
    for d in BASH_PLUGIN_DIRS:
        for p in sorted(d.iterdir()):
            if p.is_file() and not re.match(r"[0-9._]", p.name) and not p.name.endswith(("~", ".yaml")):
                files.append(p)
    return files


@cache
def yaml_plugin_files() -> list[Path]:
    """The YAML plug-ins of the repository (scripts.d)."""
    return sorted((REPO_ROOT / "scripts.d").glob("c-*.yaml"))
