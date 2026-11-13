"""Download protocols by name. Adding one: a module with a
scbi.sources.archive.base.Downloader and one entry in IMPLEMENTATIONS."""

from __future__ import annotations

from scbi.sources.archive.base import Downloader
from scbi.sources.archive.copy import Copy
from scbi.sources.archive.curl import Curl

IMPLEMENTATIONS: list[Downloader] = [Copy(), Curl()]

BY_NAME: dict[str, Downloader] = {name: impl for impl in IMPLEMENTATIONS for name in impl.names}


def get(name: str) -> Downloader | None:
    return BY_NAME.get(name)
