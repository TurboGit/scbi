"""YAML plug-in format.

A plug-in ``<name>.yaml`` is a mapping. Reserved keys:

    plugin:       the plug-in name (optional, must match the file name)
    vars:         global variables {NAME: value}
    variants:     variants including other variants {all: [ai, hdr, jxl]}
    inherit:      [{from: P, hooks: [..], custom-hooks: [..], no-variant: true,
                    name: N}]
    with-variants:  {native: {packages: [os@-x:[v], ...], env: [<env op>...]}}
    functions:    {name: {params: [A, B], run: <shell>}}

Every other key is a hook of the catalog (scbi.plugin.catalog), including
``pre-<step>`` / ``post-<step>``. A hook value is either its body (the
plain hook ``<plugin>-<hook>``) or a mapping of qualifiers, each naming
exactly one of ``_`` (plain), ``common``, ``default`` or a variant, and
``cross`` holding the same kind of mapping (or a body) for host != target.

Bodies by hook kind:

    command  shell script (string); parameters of the catalog are set as
             variables (PREFIX, TARGET, VARIANT...).
    value    list of lines (or a single string); ``vcs`` and ``archive``
             may also be given as a mapping of their fields.
    env      list of actions: "<verb> <args>" (add-to-var, prepend-to-var,
             set-var, define-var, unset-var, export, system-compiler,
             target-env, no-target-env, mkdir, import).

In value and env lists an item can be guarded: ``{"if <cond>": item}`` or
``{"if <cond>": [items]}`` (see scbi.plugin.expr).

All scalars are read as strings (no YAML booleans or numbers). The driver
only reads plug-ins; ``dump`` is used by the migration converter.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from scbi.plugin import catalog, construct
from scbi.plugin.catalog import COMMAND, VALUE
from scbi.plugin.construct import RECORD_MIN, RECORDS, DefinitionError
from scbi.plugin.formats import PluginFormatError
from scbi.plugin.model import (
    PLAIN,
    Commands,
    EnvOp,
    EnvOps,
    Guarded,
    HookKey,
    Inherit,
    WithVariant,
    PluginDef,
    SourceEntry,
    Values,
)

RESERVED = ("plugin", "vars", "variants", "inherit", "with-variants", "functions")
PLAIN_KEY = "_"
CROSS_KEY = "cross"

#  Value hooks usually holding a single value, dumped as a scalar
SCALAR_HOOKS = ("out-of-tree", "only-explicit-build", "prefix", "aggregate", "propagate-version", "plan")


class FormatError(PluginFormatError):
    """An invalid YAML plug-in (message with its location)."""


# ----------------------------------------------------------- YAML dialect


class _Loader(yaml.SafeLoader):
    pass


class _Dumper(yaml.SafeDumper):
    pass


#  No implicit typing: every scalar is a string
_Loader.yaml_implicit_resolvers = {}
_Dumper.yaml_implicit_resolvers = {}


def _str_representer(dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_representer)


# ------------------------------------------------------------------ load


def _err(where: str, msg: str) -> FormatError:
    return FormatError(f"{where}: {msg}")


def _as_list(value, where: str) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, (str, dict)):
        return [value]
    if value is None:
        return []
    raise _err(where, f"expected a list, got {type(value).__name__}")


def _built(where: str, build, *args):
    """A model object built by scbi.plugin.construct, its errors located."""
    try:
        return build(*args)
    except DefinitionError as e:
        raise _err(where, str(e)) from None


def _guarded(item: dict, where: str, convert) -> Guarded:
    if len(item) != 1:
        raise _err(where, f"a guarded item must have a single 'if <cond>' key: {item}")
    (key, value), = item.items()
    if not isinstance(key, str) or not key.startswith("if "):
        raise _err(where, f"unexpected mapping in list: {item}")
    cond = key[3:].strip()
    _built(where, construct.guarded, cond, (), None)  # the condition first
    return Guarded(cond, tuple(convert(i, where) for i in _as_list(value, where)))


def _value_item(item, where: str):
    if isinstance(item, dict):
        return _guarded(item, where, _value_item)
    if isinstance(item, str):
        return _built(where, construct.value, item)
    if item is None:
        return ""
    raise _err(where, f"unexpected value {item!r}")


def _source_item(item, where: str):
    """An entry of the source-tree hook (a mapping from/to/exclude) or a
    guarded list of entries."""
    if isinstance(item, dict) and len(item) == 1 and str(next(iter(item))).startswith("if "):
        return _guarded(item, where, _source_item)
    if isinstance(item, dict):
        return _built(where, construct.source_entry, item)
    raise _err(where, f"a source-tree entry (from, to, exclude) is expected, not {item!r}")


def _env_item(item, where: str):
    if isinstance(item, dict):
        return _guarded(item, where, _env_item)
    if not isinstance(item, str):
        raise _err(where, f"unexpected environment action {item!r}")
    return _built(where, construct.env_action, item)


#  where -> line of the scalar in the file (1-based, first line of the
#  content for a block scalar), for the messages of command bodies
_LINES: dict[str, int] = {}


def _scalar_lines(node, where: str, out: dict[str, int]) -> None:
    if isinstance(node, yaml.MappingNode):
        for k, v in node.value:
            _scalar_lines(v, f"{where}.{k.value}", out)
    elif isinstance(node, yaml.ScalarNode):
        out[where] = node.start_mark.line + (2 if node.style in ("|", ">") else 1)


def _commands(text, where: str) -> Commands:
    if not isinstance(text, str):
        raise _err(where, "a body in the command language (string) is expected")
    return _built(where, construct.commands, text, _LINES.get(where, 1))


def _body(hook: str, value, where: str):
    kind = catalog.spec(hook).kind
    if kind == COMMAND:
        return _commands(value, where)
    if hook == "source-tree":
        return Values(tuple(_source_item(i, where) for i in _as_list(value, where)))
    if kind == VALUE:
        if isinstance(value, dict) and construct.is_record(hook, value):
            return _built(where, construct.record, hook, value)
        return Values(tuple(_value_item(i, where) for i in _as_list(value, where)))
    return EnvOps(tuple(_env_item(i, where) for i in _as_list(value, where)))


def _is_qualifier_map(hook: str, value) -> bool:
    if not isinstance(value, dict):
        return False
    if construct.is_record(hook, value) or construct.is_source_entry(hook, value):
        return False
    #  a guarded single item is a list item, not a qualifier map
    return not (len(value) == 1 and str(next(iter(value))).startswith("if "))


def _hooks(hook: str, value, where: str, cross: bool, out: dict) -> None:
    if not _is_qualifier_map(hook, value):
        out[HookKey(hook, PLAIN, cross)] = _body(hook, value, where)
        return
    for q, body in value.items():
        q = str(q)
        w = f"{where}.{q}"
        if q == CROSS_KEY:
            if cross:
                raise _err(w, "nested cross")
            _hooks(hook, body, w, True, out)
        else:
            qualifier = PLAIN if q == PLAIN_KEY else q
            _built(w, construct.check_qualifier, hook, qualifier)
            out[HookKey(hook, qualifier, cross)] = _body(hook, body, w)


def load(path: Path) -> PluginDef:
    path = Path(path)
    name = path.name[: -len(".yaml")] if path.name.endswith(".yaml") else path.name
    try:
        text = path.read_text()
        data = yaml.load(text, Loader=_Loader) or {}
        node = yaml.compose(text, Loader=_Loader)
    except yaml.YAMLError as e:
        raise FormatError(f"{path}: {e}") from None
    if not isinstance(data, dict):
        raise FormatError(f"{path}: a mapping is expected")
    _LINES.clear()
    if node is not None:
        _scalar_lines(node, str(path), _LINES)
    try:
        return from_data(name, data, str(path))
    finally:
        _LINES.clear()


def from_data(name: str, data: dict, where: str = "") -> PluginDef:
    where = where or name
    if data.get("plugin", name) != name:
        raise _err(where, f"plugin name {data['plugin']!r} does not match the file name {name!r}")
    pdef = PluginDef(name)

    for k, v in (data.get("vars") or {}).items():
        if isinstance(v, list):
            if not all(isinstance(i, (str, int, float)) and not isinstance(i, bool) for i in v):
                raise _err(f"{where}.vars.{k}", "a text or a list of texts is expected")
            pdef.variables[str(k)] = tuple(str(i) for i in v)
        elif isinstance(v, dict):
            raise _err(f"{where}.vars.{k}", "a text or a list of texts is expected")
        else:
            pdef.variables[str(k)] = "" if v is None else str(v)

    for vname, members in (data.get("variants") or {}).items():
        w = f"{where}.variants.{vname}"
        pdef.variants[str(vname)] = _built(w, construct.variant_members,
                                           [str(m) for m in _as_list(members, w)])

    for i, inh in enumerate(_as_list(data.get("inherit"), f"{where}.inherit")):
        if isinstance(inh, str):
            inh = {"from": inh}
        if "from" not in inh:
            raise _err(f"{where}.inherit[{i}]", "missing 'from'")
        pdef.inherits.append(
            Inherit(
                inh["from"],
                tuple(_as_list(inh.get("hooks"), where)),
                tuple(_as_list(inh.get("custom-hooks"), where)),
                str(inh.get("no-variant", "false")).lower() in ("true", "yes"),
                inh.get("name"),
            )
        )

    for vname, v in (data.get("with-variants") or {}).items():
        w = f"{where}.with-variants.{vname}"
        v = v or {}
        pdef.with_variants.append(
            WithVariant(
                str(vname),
                tuple("" if p is None else str(p) for p in _as_list(v.get("packages"), w)),
                tuple(_env_item(i, w) for i in _as_list(v.get("env"), w)),
            )
        )

    for fname, f in (data.get("functions") or {}).items():
        w = f"{where}.functions.{fname}"
        if isinstance(f, str):
            _LINES.setdefault(f"{w}.run", _LINES.get(w, 1))
            f = {"run": f}
        run = f.get("run", "")
        if not isinstance(run, str):
            raise _err(f"{w}.run", "a body in the command language (string) is expected")
        pdef.functions[str(fname)] = _built(f"{w}.run", construct.function, _as_list(f.get("params"), w),
                                           run, _LINES.get(f"{w}.run", 1))

    for key, value in data.items():
        if key in RESERVED:
            continue
        if not catalog.is_hook(key):
            raise _err(where, f"unknown hook {key!r}")
        _hooks(key, value, f"{where}.{key}", False, pdef.hooks)
    return pdef


# ------------------------------------------------------------------ dump


def _dump_items(items) -> list:
    out = []
    for it in items:
        if isinstance(it, Guarded):
            inner = _dump_items(it.items)
            out.append({f"if {it.cond}": inner[0] if len(inner) == 1 else inner})
        elif isinstance(it, EnvOp):
            out.append(" ".join((it.verb,) + it.args))
        elif isinstance(it, SourceEntry):
            entry: dict = {"from": it.from_} if it.from_ else {}
            if it.to != "." or not it.from_:
                entry["to"] = it.to
            if it.exclude:
                entry["exclude"] = list(it.exclude)
            out.append(entry)
        else:
            out.append(str(it))
    return out


def _dump_body(hook: str, body):
    if isinstance(body, Commands):
        return body.script
    if isinstance(body, EnvOps):
        return _dump_items(body.ops)
    items = _dump_items(body.items)
    if hook in RECORDS and all(isinstance(i, str) for i in items) and \
            RECORD_MIN[hook] <= len(items) <= len(RECORDS[hook]):
        return dict(zip(RECORDS[hook], items))
    if hook in SCALAR_HOOKS and len(items) == 1 and isinstance(items[0], str):
        return items[0]
    return items


def to_data(pdef: PluginDef) -> dict:
    """The plug-in as YAML data, keys in the canonical order
    (catalog.FORMAT_ORDER)."""
    data: dict = {"plugin": pdef.name}
    if pdef.inherits:
        lst = []
        for inh in pdef.inherits:
            d: dict = {"from": inh.parent}
            if inh.hooks:
                d["hooks"] = list(inh.hooks)
            if inh.custom_hooks:
                d["custom-hooks"] = list(inh.custom_hooks)
            if inh.no_variant:
                d["no-variant"] = "true"
            if inh.name:
                d["name"] = inh.name
            lst.append(d)
        data["inherit"] = lst
    if pdef.variables:
        data["vars"] = {k: list(v) if isinstance(v, tuple) else v for k, v in pdef.variables.items()}
    if pdef.functions:
        data["functions"] = {
            n: ({"params": list(f.params)} if f.params else {}) | {"run": f.script}
            for n, f in pdef.functions.items()
        }
    if pdef.variants:
        data["variants"] = {v: list(m) for v, m in pdef.variants.items()}
    if pdef.with_variants:
        data["with-variants"] = {
            v.name: {"packages": list(v.packages), **({"env": _dump_items(v.env)} if v.env else {})}
            for v in pdef.with_variants
        }

    by_hook: dict[str, dict[HookKey, object]] = {}
    rank = {"common": 0, PLAIN: 1, "default": 2}  # as yamlwrite.QUALIFIER_RANK
    for key in sorted(pdef.hooks, key=lambda k: (catalog.format_rank(k.hook), k.hook, k.cross, rank.get(k.qualifier, 3), k.qualifier)):
        by_hook.setdefault(key.hook, {})[key] = pdef.hooks[key]

    for hook, entries in by_hook.items():
        if len(entries) == 1 and next(iter(entries)) == HookKey(hook):
            body = _dump_body(hook, entries[HookKey(hook)])
            #  a plain body that would read as a qualifier map is written
            #  in qualifier form
            if not _is_qualifier_map(hook, body):
                data[hook] = body
                continue
        qmap: dict = {}
        cmap: dict = {}
        for key, body in entries.items():
            target = cmap if key.cross else qmap
            target[key.qualifier or PLAIN_KEY] = _dump_body(hook, body)
        if cmap:
            qmap[CROSS_KEY] = cmap
        data[hook] = qmap
    return data


def dump(pdef: PluginDef) -> str:
    """The canonical YAML text of the plug-in (scbi.plugin.yamlwrite)."""
    from scbi.plugin.yamlwrite import write

    return write(to_data(pdef))
