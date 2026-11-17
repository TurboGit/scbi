"""scbi show --resolved: the plug-in of a module resolved for its module
reference in the build plan.

The hooks are selected as the driver selects them for the module variant
and the target (scbi.plugin.resolve): inheritance, OS variants
(``with-variants``), variants including others, ``common`` and ``cross``
applied. A plain hook is written for each: the selected one, or for a
cumulative hook the items of all the selected ones in order (the bodies
of a cumulative command hook, ``run``, one after the other). In the value
and environment lists the ``if`` guards are evaluated for the module (an
item whose guard cannot be evaluated here is kept with it); the bodies of
the command hooks and the functions are kept as written. The result is a
YAML plug-in without variants.
"""

from __future__ import annotations

from scbi.hooks import expand as _expand
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import GuardContext
from scbi.modref import parse_module_ref
from scbi.plugin import catalog, expr, yamlfmt, yamlwrite
from scbi.plugin.lift import parse_hook_name
from scbi.plugin.model import Commands, EnvOps, Guarded, HookKey, LocalAssign, PluginDef, Values
from scbi.plugin.resolve import get_hook, variant_hooks


class ResolveError(Exception):
    pass


def _select(items, ctx: HookContext) -> list:
    """The items whose guards are true (flattened); the local variables
    (``NAME = ...``) are kept and set for the following guards; a guard
    which cannot be evaluated is kept."""
    guard = GuardContext(ctx)
    out: list = []
    for it in items:
        if isinstance(it, Guarded):
            try:
                ok = expr.evaluate(it.cond, guard)
            except Exception:  # noqa: BLE001 - not known here (dir(), a failing function...)
                out.append(Guarded(it.cond, tuple(_select(it.items, ctx))))
                continue
            if ok:
                out += _select(it.items, ctx)
            continue
        if isinstance(it, LocalAssign):
            try:
                ctx.locals[it.name] = _expand.expand(it.text, ctx)
            except Exception:  # noqa: BLE001
                ctx.locals.pop(it.name, None)
        out.append(it)
    return out


def _merge(bodies: list):
    """One body from the bodies of a cumulative hook."""
    if all(isinstance(b, Values) for b in bodies):
        return Values(tuple(i for b in bodies for i in b.items))
    if all(isinstance(b, EnvOps) for b in bodies):
        return EnvOps(tuple(i for b in bodies for i in b.ops))
    if all(isinstance(b, Commands) for b in bodies):
        scripts = [b.script.rstrip("\n") for b in bodies if not b.is_nop()]
        return Commands("\n".join(scripts) if scripts else "true")
    raise ResolveError("hook bodies of different kinds")


def _no_op(hook: str, spec, body) -> bool:
    """A hook doing the same as no hook (the placeholders of the OS
    variants...): an empty cumulative list, a pre-/post- step doing
    nothing. A step doing nothing is kept (without it the generic step
    would run)."""
    if spec is not None and spec.cumulative and isinstance(body, (Values, EnvOps)):
        return not (body.items if isinstance(body, Values) else body.ops)
    return hook.startswith(("pre-", "post-")) and isinstance(body, Commands) and body.is_nop()


def _hook_names(registry, module: str) -> list[str]:
    """The hooks the module defines or inherits, in the canonical order."""
    names = {key.hook for f in registry.functions if (key := parse_hook_name(module, f)) is not None}
    return sorted(names, key=lambda h: (catalog.format_rank(h), h))


def _chain(registry, module: str, seen: set[str] | None = None) -> list[PluginDef]:
    """The definitions of the module and of the plug-ins it inherits
    (recursively), the module first."""
    seen = set() if seen is None else seen
    if module in seen or module not in registry.definitions:
        return []
    seen.add(module)
    result = [registry.definitions[module]]
    for parent in registry.inherits.get(module, []):
        result += _chain(registry, parent, seen)
    return result


def resolve(driver, modref: str) -> tuple[PluginDef, str]:
    """The resolved plug-in of the module and the header comment."""
    given = (parse_module_ref(modref).to_bash_array() + [""] * 4)[:4]
    module = given[0]
    registry = driver.registry
    if not registry.load_module(module):
        raise ResolveError(f"{module}: plug-in not found")
    #  the variant and version given, else the ones of the build plan
    _, variant, kind, ref = (driver.plan.module_ref(module) + [""] * 4)[:4]
    if "/" in modref:
        variant = given[1]
    if ":" in modref:
        kind, ref = given[2], given[3]
    variant = variant or "default"
    runner = driver.runner()
    cross = runner.cross
    target = driver.get("SCBI_TARGET")
    prefix = f"{driver.get('SCBI_BDIR')}/{module}/{target}-{variant}/install"

    pdef = PluginDef(name=module)
    for d in reversed(_chain(registry, module)):
        pdef.variables.update(d.variables)
        pdef.functions.update(d.functions)

    for hook in _hook_names(registry, module):
        spec = catalog.HOOKS.get(hook)
        if spec is not None and spec.cumulative:
            fcts = variant_hooks(registry, module, hook, variant, cross)
        else:
            fct = get_hook(registry, module, variant, hook, cross)
            fcts = [fct] if fct else []
        bodies = [registry.functions[f] for f in fcts]
        if not bodies:
            continue
        body = bodies[0] if len(bodies) == 1 else _merge(bodies)
        if isinstance(body, (Values, EnvOps)):
            params = [prefix, target, variant] + ([kind, ref] if hook == "patches" else [])
            ctx = runner.context(module, variant, hook if spec is not None else "build", params, driver.plan)
            if isinstance(body, Values):
                body = Values(tuple(_select(body.items, ctx)))
            else:
                body = EnvOps(tuple(_select(body.ops, ctx)))
        if _no_op(hook, spec, body):
            continue
        pdef.hooks[HookKey(hook)] = body

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
