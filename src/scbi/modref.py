"""Module references.

A module reference has the form ``[for_module=]name[/variants][:version]``
(see doc/scbi.tex, section "Module reference"). This is the port of
``parse-module-ref``, ``all-variants``, ``all-variants-v`` and ``has-variant``
from scripts.d/0_runtime.

Note that, as in the Bash implementation, ``parse_module_ref`` does not
handle the ``for_module=`` prefix: it stays part of the module name and is
interpreted when registering a plan (``SCBI_MODVER`` keys).
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_VARIANT = "default"

#  Version kinds
KIND_NONE = "NONE"
KIND_DEV = "DEV"
KIND_VERSION = "VERSION"  # archive version (``:#1.0``)
KIND_BRANCH = "BRANCH"  # VCS reference (branch, tag, SHA-1) or keyword


@dataclass(frozen=True)
class ModuleRef:
    module: str
    variant: str = DEFAULT_VARIANT
    kind: str = KIND_NONE
    version: str = "NONE"

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
    """Port of ``parse-module-ref`` (scripts.d/0_runtime)."""
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

    return ModuleRef(module, variant, kind, version)


def all_variants(variants: str) -> list[str]:
    """Port of ``all-variants-v``: list of variants, empty for default."""
    if variants == DEFAULT_VARIANT:
        return []
    return variants.replace(".", " ").split()


def has_variant(variants: str, variant: str) -> bool:
    """Port of ``has-variant``."""
    return variant in all_variants(variants)
