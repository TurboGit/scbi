"""The VCS implementations by name (the protocol field of the vcs hook).
Adding a VCS: one module implementing scbi.sources.vcs.base.Vcs and one
entry in IMPLEMENTATIONS."""

from __future__ import annotations

import os

from scbi.sources.vcs.base import Vcs
from scbi.sources.vcs.git import Git
from scbi.sources.vcs.hg import Mercurial
from scbi.sources.vcs.svn import Subversion

#  in the order of vcs-build-id (.git, .svn, .hg)
IMPLEMENTATIONS: list[Vcs] = [Git(), Subversion(), Mercurial()]

BY_NAME: dict[str, Vcs] = {name: impl for impl in IMPLEMENTATIONS for name in impl.names}


def get(name: str) -> Vcs | None:
    return BY_NAME.get(name)


def detect(directory: str) -> Vcs | None:
    """The VCS of a checkout, from its marker directory (.git...), in the
    order of vcs-build-id."""
    for impl in IMPLEMENTATIONS:
        if impl.marker and os.path.isdir(os.path.join(directory, impl.marker)):
            return impl
    return None
