"""Listing of the build plan (port of _internal_list-build-plan and
display-build-plan, scripts.d/9_versions)."""

from __future__ import annotations

import re

from scbi.bashcompat import assoc_keys, words
from scbi.plan import PlanState


def list_build_plan(plan: PlanState, kind: str = "", regex: str = "") -> list[str]:
    """Lines of the plan, sorted; ``kind`` "history" adds the plans each
    reference comes from; ``regex`` selects the modules."""
    rows: list[tuple[str, str]] = []
    width = 0
    for module in assoc_keys(plan.modver):
        if module.endswith((".skip", ".keep")):
            continue
        if regex:
            try:
                if not re.search(regex, module):
                    continue
            except re.error:
                continue
        fm = module.rsplit("=", 1)[0] if "=" in module else module
        ref = plan.modver[module]
        if plan.modver.get(f"{module}.skip") == "yes":
            ref = (ref.rsplit(":", 1)[0] if ":" in ref else ref) + ":skip"
        msg = f"@for {fm} use {ref}" if fm != module else ref
        width = max(width, len(msg))

        hist = ""
        if kind == "history":
            entries = [e for e in " ".join(words(plan.plan_hist.get(module, ""))).split(";") if e]
            entries = [w for e in entries for w in words(e)]
            for i, entry in enumerate(reversed(entries)):
                data = words(entry.replace(",", " "))
                first = data[0] if data else ""
                if i == 0:
                    hist += f"{first} "
                else:
                    m = data[1] if len(data) > 1 else ""
                    m2 = m.split("/", 1)[1] if "/" in m else m
                    if m2 == m:
                        m2 = m.split(":", 1)[1] if ":" in m else m
                    hist += f"[{first} | {m2}] "
        rows.append((msg, hist))
    return sorted(f"{msg:<{width}} {hist}" for msg, hist in rows)


def display_build_plan(plan: PlanState, kind: str = "", regex: str = "") -> list[str]:
    count = sum(1 for m in plan.modver if not m.endswith((".skip", ".keep")))
    return [f"There is {count} module(s) in the plan", *list_build_plan(plan, kind, regex)]
