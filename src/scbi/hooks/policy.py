"""When may the driver use the Python ports of the runtime functions?

``define-var`` and the other runtime helpers are extension points: a user
may redefine them (globally in a runtime file, an environment file or a
plug-in) for instance to capture the environment of the modules. The
Python ports (env.py, hooks/builtins.py) are used only when every ported
function visible to the hooks is the reference one; otherwise the
environment actions are run by Bash so that the user definitions apply.

A redefinition limited to a function body (e.g. ``define-var`` redefined
inside ``module-final-step`` before calling ``plugin-call-env-hooks``)
needs nothing special: that code runs in a hook shell where YAML hooks
are rendered as Bash calls of the helpers (scbi.hooks.exec.render).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from scbi.hooks.reference import REFERENCE


def _hash(definition: str) -> str:
    return hashlib.sha256(definition.encode()).hexdigest()


def redefined(*function_maps: Mapping[str, object]) -> list[str]:
    """Ported functions whose visible definition is not the reference one.

    ``function_maps`` are given in loading order (runtime, environment
    files, plug-ins): a later definition overrides an earlier one. A missing
    function counts as redefined.
    """
    effective: dict[str, object] = {}
    for m in function_maps:
        for name in REFERENCE:
            if name in m:
                effective[name] = m[name]
    result = []
    for name, ref in REFERENCE.items():
        definition = effective.get(name)
        if not isinstance(definition, str) or _hash(definition) != ref:
            result.append(name)
    return result


def python_env_allowed(*function_maps: Mapping[str, object]) -> bool:
    """True when environment actions can be evaluated in Python."""
    return not redefined(*function_maps)


def is_reference(name: str, *function_maps: Mapping[str, object]) -> bool:
    """True when the visible definition of the ported runtime function
    ``name`` (REFERENCE or PORTED) is the reference one; ``function_maps``
    in loading order as for ``redefined``."""
    from scbi.hooks.reference import PORTED

    ref = REFERENCE.get(name) or PORTED[name]
    definition = None
    for m in function_maps:
        if name in m:
            definition = m[name]
    return isinstance(definition, str) and _hash(definition) == ref
