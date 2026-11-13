"""Plug-in file formats.

The driver works on the plug-in model (scbi.plugin.model) only. A format
is a reader turning a file ``<module><suffix>`` into a
:class:`~scbi.plugin.model.PluginDef`; its syntax stays in its reader
module (scbi.plugin.yamlfmt for YAML), the checks common to all formats
are in scbi.plugin.construct. Adding a format = one reader module and one
entry in ``FORMATS``.

The legacy Bash plug-ins (file ``<module>`` without suffix) are not a
format: they are sourced by Bash (scbi.plugin.legacy, Registry._source).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scbi.plugin.model import PluginDef


class PluginFormatError(Exception):
    """A plug-in file which cannot be read (message with its location)."""


@dataclass(frozen=True)
class Format:
    name: str
    suffix: str
    #  reads a file, raises PluginFormatError
    load: Callable[[Path], PluginDef]


def _yaml_load(path: Path) -> PluginDef:
    from scbi.plugin import yamlfmt

    return yamlfmt.load(path)  # yamlfmt.FormatError is a PluginFormatError


#  In order of preference when several files exist for a module
FORMATS: tuple[Format, ...] = (Format("yaml", ".yaml", _yaml_load),)


def format_of(path: Path | str) -> Format | None:
    """The format of a plug-in file (None: not a plug-in definition file,
    e.g. a legacy Bash plug-in)."""
    name = Path(path).name
    for f in FORMATS:
        if name.endswith(f.suffix) and len(name) > len(f.suffix):
            return f
    return None


def module_name(path: Path | str) -> str:
    """The module of a plug-in file."""
    name = Path(path).name
    f = format_of(name)
    return name[: -len(f.suffix)] if f else name


def find(directory: Path, module: str) -> Path | None:
    """The definition file of ``module`` in ``directory`` (any format)."""
    for f in FORMATS:
        path = Path(directory) / f"{module}{f.suffix}"
        if path.is_file():
            return path
    return None


def load(path: Path) -> PluginDef:
    """The definition of the plug-in file ``path``."""
    f = format_of(path)
    if f is None:
        raise PluginFormatError(f"{path}: not a plug-in definition file")
    return f.load(Path(path))
