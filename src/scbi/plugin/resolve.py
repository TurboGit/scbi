"""Selection of the hook implementations for a module variant.

Ports of ``get-hook`` / ``_internal_get-hook`` (scripts.d/5_tools) and
``plugin-get-variant-hooks`` (scripts.d/0_runtime). Hooks are looked up by
composing function names, exactly as the Bash driver does, in the
namespace of the loaded plug-ins (a Registry, or any object with an
``fn_exists(name)`` method).
"""

from __future__ import annotations

from typing import Protocol

from scbi.modref import all_variants


class Namespace(Protocol):
    def fn_exists(self, name: str) -> bool: ...


def lookup_variants(ns, module: str, variant: str) -> list[str]:
    """Variants to look hooks up for, in order.

    The variants of ``variant`` (``default`` if none), each one followed by
    the variants it includes (``variants:`` of the plug-in, recursively),
    duplicates removed. A namespace without ``variant_members`` (legacy Bash
    semantics) gives just the variants of ``variant``.
    """
    base = all_variants(variant) or ["default"]
    members = getattr(ns, "variant_members", None)
    if members is None:
        return base
    result: list[str] = []

    def add(v: str, stack: tuple[str, ...]) -> None:
        if v in stack:
            raise ValueError(f"{module}: cycle in variants: {' -> '.join(stack + (v,))}")
        if v not in result:
            result.append(v)
        for m in members(module, v):
            add(m, stack + (v,))

    for v in base:
        add(v, ())
    return result


def _variant_hook(ns: Namespace, module: str, variant: str, step: str, cross: bool) -> str:
    """Port of ``_internal_get-hook``."""
    if cross:
        name = f"{module}-{variant}-cross-{step}"
        if ns.fn_exists(name):
            return name
        name = f"{module}-cross-{step}"
        if ns.fn_exists(name):
            return name
    name = f"{module}-{variant}-{step}"
    if ns.fn_exists(name):
        return name
    return ""


def get_hook(ns: Namespace, module: str, variant: str, step: str, cross: bool = False) -> str:
    """Port of ``get-hook``: the hook function to call, or "".

    ``cross`` is true when SCBI_HOST != SCBI_TARGET.
    """
    hook = ""
    for v in lookup_variants(ns, module, variant):
        hook = _variant_hook(ns, module, v, step, cross)
        if hook:
            break
    if not hook and ns.fn_exists(f"{module}-{step}"):
        hook = f"{module}-{step}"
    return hook


def variant_hooks(ns: Namespace, module: str, hook: str, variant: str, cross: bool = False) -> list[str]:
    """Port of ``plugin-get-variant-hooks``: all hook functions to call.

    The ``common`` hook (not for the native variant), then the hook of each
    selected variant (or ``default``), then the plain hook if no variant
    specific hook was found.
    """
    result: list[str] = []
    candidates = ([] if variant == "native" else ["common"]) + lookup_variants(ns, module, variant)
    varfound = False

    for v in candidates:
        fct = ""
        if cross and ns.fn_exists(f"{module}-{v}-cross-{hook}"):
            fct = f"{module}-{v}-cross-{hook}"
        elif ns.fn_exists(f"{module}-{v}-{hook}"):
            fct = f"{module}-{v}-{hook}"
        if fct:
            if v not in ("common", "default"):
                varfound = True
            result.append(fct)

    if not varfound:
        if cross and ns.fn_exists(f"{module}-cross-{hook}"):
            result.append(f"{module}-cross-{hook}")
        elif ns.fn_exists(f"{module}-{hook}"):
            result.append(f"{module}-{hook}")

    return result
