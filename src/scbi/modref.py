"""Module references.

A module reference has the form
``[for_module=][host@]name[/variants][:version]``
(see doc/scbi.tex, section "Module reference"). This is the port of
``parse-module-ref``, ``all-variants``, ``all-variants-v`` and ``has-variant``
from scripts.d/0_runtime.

Note that, as in the Bash implementation, ``parse_module_ref`` does not
handle the ``for_module=`` prefix: it stays part of the module name and is
interpreted when registering a plan (``SCBI_MODVER`` keys).

``host@`` (a dependency): the build of the module for the host, whatever
the target. It is not part of the module name (``ModuleRef.host``).

``purge@`` (a module of the command line only): the module purged before
it is built. It is not part of the reference: removed by the driver
(``split_purge``) before the reference is used.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_VARIANT = "default"

#  Version kinds
KIND_NONE = "NONE"
KIND_DEV = "DEV"
KIND_VERSION = "VERSION"  # archive version (``:#1.0``)
KIND_BRANCH = "BRANCH"  # VCS reference (branch, tag, SHA-1) or keyword

#  Prefix of a dependency built for the host
HOST_PREFIX = "host@"
#  Prefix of a module of the command line purged before its build
PURGE_PREFIX = "purge@"


@dataclass(frozen=True)
class ModuleRef:
    module: str
    variant: str = DEFAULT_VARIANT
    kind: str = KIND_NONE
    version: str = "NONE"
    #  host@: the build of the module for the host
    host: bool = False

    @property
    def variants(self) -> list[str]:
        return all_variants(self.variant)

    def to_bash_array(self) -> list[str]:
        """Same content as the Bash array built by parse-module-ref.

        The Bash array is built with unquoted expansions, so empty or
        blank-containing fields are dropped or split.
        """
        return " ".join([self.module, self.variant, self.kind, self.version]).split()


def parse_module_ref(modref: str) -> ModuleRef:
    """Port of ``parse-module-ref`` (scripts.d/0_runtime), plus the
    ``host@`` prefix."""
    host = is_host_prefixed(modref)
    if host:
        modref = modref[len(HOST_PREFIX):]
    if ":" not in modref:
        kind = KIND_NONE
        version = "NONE"
        module = modref
    else:
        ver = modref.split(":", 1)[1]  # ${MODREF#*:}
        if ver == "dev":
            kind, version = KIND_DEV, "dev"
        elif ver[:1] == "#":
            kind, version = KIND_VERSION, ver[1:]
        else:
            kind, version = KIND_BRANCH, ver
        module = modref.split(":", 1)[0]  # ${MODREF%%:*}

    if "/" not in module:
        variant = DEFAULT_VARIANT
    else:
        variant = module.split("/", 1)[1]  # ${module#*/}
        module = module.rsplit("/", 1)[0]  # ${module%/*}

    return ModuleRef(module, variant, kind, version, host)


def is_host_prefixed(modref: str) -> bool:
    """A ``host@`` reference (the dependency built for the host)."""
    return modref.startswith(HOST_PREFIX)


def split_purge(modref: str) -> tuple[str, bool]:
    """The reference without its ``purge@`` prefix, and whether it had
    one."""
    if modref.startswith(PURGE_PREFIX):
        return modref[len(PURGE_PREFIX):], True
    return modref, False


def strip_host(modref: str) -> str:
    """The reference without its ``host@`` prefix."""
    return modref[len(HOST_PREFIX):] if is_host_prefixed(modref) else modref


def all_variants(variants: str) -> list[str]:
    """Port of ``all-variants-v``: list of variants, empty for default."""
    if variants == DEFAULT_VARIANT:
        return []
    return variants.replace(".", " ").split()


def has_variant(variants: str, variant: str) -> bool:
    """Port of ``has-variant``."""
    return variant in all_variants(variants)
