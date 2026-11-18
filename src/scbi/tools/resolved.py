"""scbi show --resolved: the plug-in of a module resolved for its module
reference (the variant and version given, else the ones of the build
plan) and the target (scbi.plugin.resolved), written as a YAML plug-in
with a header comment.
"""

from __future__ import annotations

from scbi.modref import parse_module_ref
from scbi.plugin import yamlfmt, yamlwrite
from scbi.plugin.model import PluginDef
from scbi.plugin.resolved import ResolveError, resolve_module


def resolve(driver, modref: str) -> tuple[PluginDef, str]:
    """The resolved plug-in of the module and the header comment."""
    given = (parse_module_ref(modref).to_bash_array() + [""] * 4)[:4]
    module = given[0]
    if not driver.registry.load_module(module):
        raise ResolveError(f"{module}: plug-in not found")
    #  the variant and version given, else the ones of the build plan
    _, variant, kind, ref = (driver.plan.module_ref(module) + [""] * 4)[:4]
    if "/" in modref:
        variant = given[1]
    if ":" in modref:
        kind, ref = given[2], given[3]
    variant = variant or "default"
    pdef = resolve_module(driver, module, variant, kind, ref)

    target = driver.get("SCBI_TARGET")
    cross = driver.runner().cross
    plan = driver.get("SCBI_PLAN")
    version = f":{ref}" if ref and ref.upper() != "NONE" else ""
    header = [f"#  Plug-in {module} resolved for {module}/{variant}{version} (scbi show --resolved)",
              f"#  target {target}{' (cross)' if cross else ''}, plan {plan or '(none)'}"]
    return pdef, "\n".join(header)


def show(driver, modrefs: list[str]) -> int:
    status = 0
    for n, modref in enumerate(modrefs):
        try:
            pdef, header = resolve(driver, modref)
        except ResolveError as e:
            driver.log.elog(str(e))
            status = 1
            continue
        if n:
            print()
        comments = yamlwrite.Comments(header=header.split("\n"))
        print(yamlwrite.write(yamlfmt.to_data(pdef), comments), end="")
    return status
