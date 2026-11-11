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
    for v in all_variants(variant) or ["default"]:
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
    candidates = ([] if variant == "native" else ["common"]) + (all_variants(variant) or ["default"])
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
