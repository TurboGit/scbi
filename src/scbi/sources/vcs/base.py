"""VCS interface and the execution context of the VCS commands.

A VCS implementation is a port of the corresponding Bash functions of
scripts.d/4_scm (<vcs>-co, <vcs>-branch, the <vcs> cases of
get-vcs-commit-id, get-vcs-ref and vcs-build-id). Adding a VCS is one
module implementing ``Vcs`` and one entry in registry.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from scbi.bashcompat import words
from scbi.sources.run import Run


#  the context of the VCS commands
VcsRun = Run


def option_list(options: str) -> list[str]:
    """``LOPTS=( ${OPTIONS//,/ } )``."""
    return words(options.replace(",", " "))


class Vcs(ABC):
    #  names selecting this VCS in the vcs hook (protocol field)
    names: tuple[str, ...] = ()
    #  get-vcs-ref: "<label> <ref> <id-kind> <commit id>"
    label = ""
    id_kind = "revision"
    #  get-vcs-display-ref: the reference shown for NONE
    default_ref = ""
    #  the tool checked by check-tool when the checkout fails
    tool = ""
    #  the directory marking a checkout of this VCS (vcs-build-id)
    marker = ""

    @abstractmethod
    def checkout(self, r: VcsRun, url: str, options: str, name: str, dir: str) -> int:
        """``<vcs>-co``: clone or update the repository in $SCBI_BDIR/.vcs and
        link it as $SCBI_BDIR/<name>/vcs."""

    @abstractmethod
    def branch(self, r: VcsRun, options: str, module: str, branch: str, dir: str,
               *, fetch: bool = True) -> int:
        """``<vcs>-branch``: switch the checkout to the branch, tag or
        revision ``branch`` (NONE: the default one); ``fetch``: get the
        new tags from the remote first (not when the repository has just
        been updated from it, nor without --update)."""

    @abstractmethod
    def commit_id(self, short: bool, dir: str, env: dict[str, str]) -> str:
        """The ``get-vcs-commit-id`` case of this VCS."""

    @abstractmethod
    def source_id(self, r: VcsRun) -> str:
        """The ``vcs-build-id`` part for a checkout of this VCS (current
        directory of ``r``)."""

    def link_src(self, r: VcsRun, module: str, ref: str) -> int:
        """Link ``src`` to the sources in the checkout (handle-sources)."""
        return r.run("ln", "-s", "vcs", "src")
