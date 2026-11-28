"""The plug-in of a module resolved for a module reference (module,
variant, kind, reference) and the target.

The hooks are selected as the driver selects them for the module variant
and the target (scbi.plugin.resolve): inheritance, OS variants
(``with-variants``), variants including others, ``common`` and ``cross``
applied. A plain hook is kept for each: the selected one, or for a
cumulative hook the items of all the selected ones in order (the bodies
of a cumulative command hook, ``run``, one after the other). In the value
and environment lists the ``if`` guards are evaluated for the module (an
item whose guard cannot be evaluated here is kept with it); the bodies of
the command hooks, the functions (of the plug-in and of the ones it
inherits) and the variables are kept as written. The result is a plug-in
definition without variants.

Used by ``scbi show --resolved`` (scbi.tools.resolved) and for the build
id of a module (scbi.sources.buildid): ``resolved_md5`` (the resolved
plug-in without its ``env`` hook, not used by the build of the module)
and ``env_md5`` (its ``env`` hook, used by the builds of the modules
depending on it).
"""

from __future__ import annotations

import hashlib
import json

from scbi.hooks import expand as _expand
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import GuardContext, set_plugin_vars
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


def _hook_body(driver, module: str, variant: str, kind: str, ref: str, hook: str):
    """The resolved body of a hook of the module (None: no hook)."""
    registry = driver.registry
    runner = driver.runner()
    cross = runner.cross
    spec = catalog.HOOKS.get(hook)
    if spec is not None and spec.cumulative:
        fcts = variant_hooks(registry, module, hook, variant, cross)
    else:
        fct = get_hook(registry, module, variant, hook, cross)
        fcts = [fct] if fct else []
    bodies = [registry.functions[f] for f in fcts]
    if not bodies:
        return None
    body = bodies[0] if len(bodies) == 1 else _merge(bodies)
    if isinstance(body, (Values, EnvOps)):
        target = driver.get("SCBI_TARGET")
        prefix = f"{driver.get('SCBI_BDIR')}/{module}/{target}-{variant}/install"
        params = [prefix, target, variant] + ([kind, ref] if hook == "patches" else [])
        ctx = runner.context(module, variant, hook if spec is not None else "build", params, driver.plan)
        try:
            set_plugin_vars(ctx, registry.plugin_variables(module))
        except Exception:  # noqa: BLE001 - not known here: the guards using them are kept
            pass
        if isinstance(body, Values):
            body = Values(tuple(_select(body.items, ctx)))
        else:
            body = EnvOps(tuple(_select(body.ops, ctx)))
    if _no_op(hook, spec, body):
        return None
    return body


def resolve_module(driver, module: str, variant: str, kind: str, ref: str) -> PluginDef:
    """The plug-in of ``module`` resolved for the module reference
    (variant, kind and reference of the version) and the target."""
    registry = driver.registry
    if not registry.load_module(module):
        raise ResolveError(f"{module}: plug-in not found")
    variant = variant or "default"
    pdef = PluginDef(name=module)
    for d in reversed(registry.chain(module)):
        pdef.variables.update(d.variables)
        pdef.functions.update(d.functions)
    for hook in _hook_names(registry, module):
        body = _hook_body(driver, module, variant, kind, ref, hook)
        if body is not None:
            pdef.hooks[HookKey(hook)] = body
    return pdef


def _cache(driver, name: str) -> dict:
    """A cache of the run, for the current build plan (a meta-module may
    load its own plan: d.plan is then another object)."""
    caches = getattr(driver, "_resolved_caches", None)
    if caches is None:
        caches = {}
        driver._resolved_caches = caches
    return caches.setdefault((name, id(driver.plan)), {})


def resolved_md5(driver, module: str, variant: str, kind: str, ref: str) -> str:
    """md5 of the canonical text of the resolved plug-in without its
    ``env`` hook (not used by the build of the module itself: see
    env_md5) and its ``license`` hook."""
    target = driver.get("SCBI_TARGET")
    key = (module, variant, kind, ref, target)
    cache = _cache(driver, "plugin")
    if key not in cache:
        pdef = resolve_module(driver, module, variant, kind, ref)
        pdef.hooks.pop(HookKey("env"), None)
        #  nor its license (information only), nor the SHA-256 of its
        #  archives (checked; the archive itself is in the build id)
        pdef.hooks.pop(HookKey("license"), None)
        pdef.hooks.pop(HookKey("archive-sha256"), None)
        #  the order of the variables and functions of the file has no
        #  meaning (the hooks are already in the canonical order): moving
        #  them must not change the build id
        pdef.variables = dict(sorted(pdef.variables.items()))
        pdef.functions = dict(sorted(pdef.functions.items()))
        #  nor the order of the dependencies (unless a local variable is
        #  set in the list: its position counts for the following items)
        for hook in ("depends", "build-depends", "tests-depends"):
            body = pdef.hooks.get(HookKey(hook))
            if isinstance(body, Values) and not any(isinstance(i, LocalAssign) for i in body.items):
                pdef.hooks[HookKey(hook)] = Values(tuple(sorted(
                    body.items, key=lambda i: json.dumps(yamlfmt._dump_items([i])))))
        text = yamlwrite.write(yamlfmt.to_data(pdef))
        cache[key] = hashlib.md5(text.encode(errors="surrogateescape")).hexdigest()
    return cache[key]


def env_md5(driver, module: str, variant: str) -> str:
    """md5 of the resolved ``env`` hook of the module (the environment it
    gives to the modules depending on it)."""
    target = driver.get("SCBI_TARGET")
    key = (module, variant, target)
    cache = _cache(driver, "env")
    if key not in cache:
        text = ""
        if driver.registry.load_module(module):
            body = _hook_body(driver, module, variant or "default", "", "", "env")
            if body is not None:
                text = json.dumps(yamlfmt._dump_items(body.ops))
        cache[key] = hashlib.md5(text.encode(errors="surrogateescape")).hexdigest()
    return cache[key]
