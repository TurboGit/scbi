"""Propagation of the meta-modules variants and versions in the plan.

Port of the meta-module part of ``rewrite-module-plan`` and of
``handle-plan-meta-module`` (scripts.d/9_versions): the variant and/or
version of a meta-module are propagated to the modules it aggregates
(``propagate-version`` hook: version, variant, both or no), recursively
for meta-modules found in the aggregated modules.

As in Bash, the modules of a round are handled against the plan as it was
at the start of the round (parallel sub-shells), then the results are
registered in order.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from scbi.bashcompat import assoc_keys, words


def may_be_meta(plugins: Path, module: str) -> bool:
    """Fast check of a meta-module (false positives are harmless).

    Bash: ``egrep -sq "function $M.*modules" $SCBI_PLUGINS/$M``; for a
    YAML plug-in, a ``modules`` key.
    """
    f = plugins / module
    if f.is_file():
        try:
            return re.search(f"function {module}.*modules", f.read_text(errors="replace")) is not None
        except re.error:
            return False
    y = plugins / f"{module}.yaml"
    if y.is_file():
        return re.search(r"(?m)^modules\s*:", y.read_text(errors="replace")) is not None
    return False


def _ref(kind: str, ref: str) -> str:
    return f":#{ref}" if kind == "VERSION" else f":{ref}"


def handle_meta(driver, runner, plan, key: str) -> list[tuple[str, str]]:
    """Port of ``handle-plan-meta-module``: (module, new reference) list."""
    plugins = Path(driver.get("SCBI_PLUGINS"))
    if not may_be_meta(plugins, key):
        return []

    value = plan.modver.get(key, "")
    mod = re.sub(r"^.*=", "", key)
    for_module = key[: len(key) - len(mod)] if key.endswith(mod) else key
    for_module = for_module.removesuffix("=")

    info = (plan.module_ref(value, for_module or "@root") + [""] * 4)[:4]
    module, variant, kind, ref = info
    if ref == "skip":
        return []
    if driver.registry.plugin_file(module) is None:
        return []
    driver.registry.load_module(module)

    prefix, target = driver.get("SCBI_PREFIX"), driver.get("SCBI_TARGET")
    mode = "version"
    v = runner.hook_value(module, variant, "propagate-version", [prefix, target, variant], plan)
    if v is not None:
        mode = v

    if ref in ("master", "NONE"):
        mode = {"version": "no", "both": "variant"}.get(mode, mode)
    if variant == "default":
        mode = {"variant": "no", "both": "version"}.get(mode, mode)
    if mode == "no":
        return []

    result = []
    for m in words("\n".join(runner.variant_values(module, variant, "modules", [prefix, target, variant], plan))):
        mref = ""
        if not plan.modver.get(m):
            if variant != "default" and mode in ("both", "variant"):
                mref = f"/{variant}"
            if mode in ("both", "version"):
                mref += _ref(kind, ref)
        else:
            s = plan.modver[m]
            sinfo = (plan.module_ref(s, module) + [""] * 4)[:4]
            s_variant, s_kind, s_ref = sinfo[1], sinfo[2], sinfo[3]
            if s_variant != "default":
                mref = f"/{s_variant}"
            elif mode in ("both", "variant") and variant != "default":
                mref = f"/{variant}"
            if s_ref != "NONE":
                mref += _ref(s_kind, s_ref)
            elif mode in ("both", "version"):
                mref += _ref(kind, ref)
        if mref:
            result.append((m, f"{m}{mref}"))
    return result


def propagate_meta_versions(driver) -> int:
    """Meta-module rounds of ``rewrite-module-plan``; returns the status."""
    plan = driver.plan
    runner = driver.runner()
    plugins = Path(driver.get("SCBI_PLUGINS"))
    mods = assoc_keys(plan.modver)
    while mods:
        snapshot = copy.deepcopy(plan)
        new: list[str] = []
        for key in mods:
            for m, modref in handle_meta(driver, runner, snapshot, key):
                plan.register(["meta", *words(m), *words(modref)], driver.is_built)
                if may_be_meta(plugins, m):
                    new.append(m)
        mods = new
    return 0
