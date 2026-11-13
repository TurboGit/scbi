"""Lift a legacy Bash plug-in into a declarative :class:`PluginDef`.

Used by the migration converter (``scbi convert``) only: the driver can
load legacy plug-ins directly. What cannot be expressed declaratively is
reported as an :class:`Issue` (the plug-in must then be fixed by hand).

Function bodies come from ``declare -f`` (normalized Bash formatting).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from scbi.bashcompat import ShellSyntaxError, shell_words
from scbi.plugin import catalog
from scbi.plugin.catalog import COMMAND, VALUE
from scbi.plugin.expr import ExprError, parse
from scbi.plugin.legacy import PluginTrace
from scbi.plugin.model import (
    ENV_VERBS,
    unknown_builtins,
    PLAIN,
    EnvOp,
    EnvOps,
    Function,
    Guarded,
    HookKey,
    Inherit,
    OsVariant,
    PluginDef,
    Commands,
    Values,
)
from scbi.plugin.registry import parse_inherit_args

_STEPS = sorted(catalog.step_names(), key=len, reverse=True)


@dataclass
class Issue:
    function: str
    message: str


@dataclass
class LiftResult:
    plugin: PluginDef
    issues: list[Issue] = field(default_factory=list)
    #  Bash hooks only calling the same hook of other variants, replaced by
    #  ``variants:``: function -> called functions
    composite: dict[str, list[str]] = field(default_factory=dict)


class _Unliftable(Exception):
    pass


# -------------------------------------------------------------- names


def parse_hook_name(plugin: str, name: str) -> HookKey | None:
    """``<plugin>[-<qualifier>][-cross]-<hook>`` -> HookKey, None if custom."""
    if not name.startswith(f"{plugin}-"):
        return None
    rest = name[len(plugin) + 1 :]
    for step in _STEPS:
        if rest == step:
            return HookKey(step)
        if rest == f"cross-{step}":
            return HookKey(step, PLAIN, True)
        if rest.endswith(f"-cross-{step}"):
            return HookKey(step, rest[: -len(step) - 7], True)
        if rest.endswith(f"-{step}"):
            return HookKey(step, rest[: -len(step) - 1])
    return None


# --------------------------------------------------------------- bodies

_PARAM = re.compile(r"^local ([A-Za-z_][A-Za-z0-9_]*)=\$\{?([0-9])\}?;?$")


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _shell_lines(lines: list[str]):
    """(line, in_heredoc) for each line; here-document bodies are raw text."""
    delimiter = None
    for ln in lines:
        if delimiter is not None:
            yield ln, True
            if ln.strip() == delimiter:
                delimiter = None
            continue
        yield ln, False
        m = _HEREDOC.search(ln)
        if m:
            delimiter = m.group(2)


def body_lines(definition: str) -> list[str]:
    """Body of a ``declare -f`` definition, dedented, one entry per line.

    ``declare -f`` indents the code by 4 spaces per level and ends simple
    commands with ";": both are removed, except in here-documents.
    """
    lines = definition.split("\n")
    #  "name () ", "{ ", body..., "}"
    out = []
    for ln, raw in _shell_lines(lines[2:-1]):
        if not raw:
            ln = ln[4:] if ln.startswith("    ") else ln.lstrip()
            if ln.endswith(";") and not ln.endswith(";;"):
                ln = ln[:-1]
        out.append(ln)
    return out


def split_params(lines: list[str]) -> tuple[list[tuple[str, int]], list[str]]:
    """Leading ``local NAME=$n`` declarations and the remaining lines."""
    params: list[tuple[str, int]] = []
    i = 0
    while i < len(lines):
        m = _PARAM.match(lines[i].strip())
        if not m:
            break
        params.append((m.group(1), int(m.group(2))))
        i += 1
    return params, lines[i:]


def _strip(line: str) -> str:
    line = line.strip()
    return line[:-1].rstrip() if line.endswith(";") else line


def _unquote(text: str) -> str:
    """Remove quotes when ``text`` is a single fully quoted word."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        inner = t[1:-1]
        if t[0] not in inner:
            return inner
    return t


_VARS = {
    "REF": "ref", "TARGET": "target", "SCBI_TARGET": "target",
    "SCBI_HOST": "host", "VARIANT": "variant", "KIND": "kind",
}


def _cond_operand(text: str, locals_: dict[str, str]) -> str:
    t = _unquote(text)
    m = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", t)
    if m:
        name = m.group(1)
        if name in locals_:
            return _cond_operand(locals_[name], {})
        if name in _VARS:
            return _VARS[name]
        return f"${name}"
    m = re.fullmatch(r"\$\(get-module-version\s+(\S+)\)", t)
    if m:
        return f"version({_unquote(m.group(1))})"
    m = re.fullmatch(r"\$\(get-build-type\s+(\S+)(?:\s+(\S+))?\)", t)
    if m:
        arg = m.group(1) + (f",{m.group(2)}" if m.group(2) else "")
        return f"build-type({arg})"
    if re.search(r"[\s()]", t) or t == "":
        return '"' + t.replace('"', '\\"') + '"'
    return t


def translate_cond(cond: str, locals_: dict[str, str]) -> str:
    """Bash test (``[[ ... ]]`` or check-module-version) -> guard syntax."""
    c = cond.strip()
    m = re.fullmatch(r"check-module-version\s+(\S+)\s+(\S+)\s+(\S+)", c)
    if m:
        op = _unquote(m.group(2))
        op = "==" if op == "=" else op
        return f"version({_unquote(m.group(1))}) {op} {_cond_operand(m.group(3), locals_)}"
    m = re.fullmatch(r"\[\[\s+(.*?)\s+\]\]", c)
    if not m:
        raise _Unliftable(f"unsupported condition: {cond}")
    inner = m.group(1)
    m = re.fullmatch(r"-[fde]\s+(\S+)", inner)
    if m:
        arg = _unquote(m.group(1))
        if "$(" in arg or any(v in arg for v in locals_):
            raise _Unliftable(f"unsupported file test: {cond}")
        return f"exists({arg})"
    words = re.findall(r"\$\([^)]*\)|\"[^\"]*\"|'[^']*'|\S+", inner)
    if len(words) != 3 or words[1] not in ("==", "!=", "=~", "="):
        raise _Unliftable(f"unsupported condition: {cond}")
    left, op, right = words
    op = "==" if op == "=" else op
    lv, rv = _cond_operand(left, locals_), _cond_operand(right, locals_)
    if {lv, rv} == {"host", "target"} and op in ("==", "!="):
        result = "cross" if op == "!=" else "not cross"
    else:
        result = f"{lv} {op} {rv}"
    try:
        parse(result)
    except ExprError as e:
        raise _Unliftable(f"cannot translate condition {cond}: {e}") from None
    return result


def _inline(text: str, locals_: dict[str, str]) -> str:
    for name, value in locals_.items():
        text = re.sub(r"\$\{" + name + r"\}|\$" + name + r"(?![A-Za-z0-9_])", lambda _: value, text)
    return text


_ASSIGN = re.compile(r"^(?:local\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


class _BodyLifter:
    """Shared structure of value and env bodies: items, guards, locals."""

    def __init__(self, lines: list[str], item, local_op=None):
        self.lines = [_strip(ln) for ln in lines if _strip(ln)]
        self.item = item  # callable(line, locals) -> item or None (skip)
        #  callable(name, value) -> item: assignments kept as items (env)
        #  instead of being inlined (values)
        self.local_op = local_op
        self.locals: dict[str, str] = {}
        self.pending_check: str | None = None

    def run(self) -> tuple:
        items, end = self.block(0, ())
        if end != len(self.lines):
            raise _Unliftable(f"unexpected line: {self.lines[end]}")
        return tuple(items)

    def block(self, i: int, stop: tuple[str, ...]) -> tuple[list, int]:
        items: list = []
        while i < len(self.lines):
            line = self.lines[i]
            if line in stop or any(line.startswith(s + " ") for s in stop):
                return items, i
            m = re.fullmatch(r"if (.*); then", line)
            if m:
                cond = self.condition(m.group(1))
                then, i = self.block(i + 1, ("else", "fi"))
                other: list = []
                if self.lines[i] == "else":
                    other, i = self.block(i + 1, ("fi",))
                if then:
                    items.append(Guarded(cond, tuple(then)))
                if other:
                    items.append(Guarded(f"not ({cond})", tuple(other)))
                i += 1
                continue
            m = re.fullmatch(r"(\[\[ .* \]\]) && (.*)", line)
            if m:
                cond = translate_cond(m.group(1), self.locals)
                inner = self.item(m.group(2), self.locals)
                if inner is None:
                    raise _Unliftable(f"unsupported guarded action: {line}")
                items.append(Guarded(cond, (inner,)))
                i += 1
                continue
            m = re.fullmatch(r"check-module-version .*", line)
            if m:
                self.pending_check = translate_cond(line, self.locals)
                i += 1
                continue
            if line in ("true", ":"):
                i += 1
                continue
            item = self.item(line, self.locals)
            if item is not None:
                items.append(item)
                i += 1
                continue
            m = _ASSIGN.match(line)
            if m and not line.startswith("export "):
                if self.local_op is not None:
                    value = _words(m.group(2))
                    if len(value) > 1:
                        raise _Unliftable(f"assignment of several words: {line}")
                    items.append(self.local_op(line.startswith("local "), m.group(1),
                                               value[0] if value else ""))
                else:
                    self.locals[m.group(1)] = _inline(_unquote(m.group(2)), self.locals)
                i += 1
                continue
            raise _Unliftable(f"unsupported line: {line}")
        return items, i

    def condition(self, text: str) -> str:
        if re.fullmatch(r"\[\[ \$\? (==|=) 0 \]\]", text.strip()):
            if self.pending_check is None:
                raise _Unliftable(f"status test without check: {text}")
            cond, self.pending_check = self.pending_check, None
            return cond
        return translate_cond(text, self.locals)


def _value_item(line: str, locals_: dict[str, str]):
    m = re.fullmatch(r"echo(?: (.*))?", line)
    if not m:
        return None
    text = _inline(m.group(1) or "", locals_)
    if "`" in text:
        raise _Unliftable(f"backquotes in value: {line}")
    #  the item is the line printed by echo (quote removal, words joined)
    return " ".join(_words(text))


def _env_item(line: str, locals_: dict[str, str]):
    line = _inline(line, locals_)
    m = re.fullmatch(r"export ([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
    if m:
        value = _words(m.group(2))
        if len(value) > 1:
            raise _Unliftable(f"export of several words: {line}")
        return EnvOp("export", (m.group(1), value[0] if value else ""))
    m = re.fullmatch(r"mkdir(?: -p)? (\S+)", line)
    if m:
        return EnvOp("mkdir", tuple(_words(m.group(1))))
    m = re.fullmatch(r"eval \$\((.*)\)", line)
    if m:
        return EnvOp("import", (m.group(1).strip(),))
    verb = line.split(None, 1)[0] if line.split() else ""
    if verb not in ENV_VERBS or verb in ("export", "mkdir", "import", "local", "assign"):
        return None
    args = _words(line)[1:]
    arity = ENV_VERBS[verb]
    if arity >= 0 and len(args) != arity:
        raise _Unliftable(f"wrong number of arguments: {line}")
    if any(re_ws.search(a) for a in args[:-1]) or (arity < 0 and any(re_ws.search(a) for a in args)):
        raise _Unliftable(f"argument with blanks: {line}")
    return EnvOp(verb, tuple(args))


re_ws = re.compile(r"\s")


def _words(text: str) -> list[str]:
    try:
        return shell_words(text)
    except ShellSyntaxError as e:
        raise _Unliftable(str(e)) from None


def _check_builtins(items) -> None:
    for it in items:
        if isinstance(it, Guarded):
            _check_builtins(it.items)
            continue
        text = " ".join(it.args) if isinstance(it, EnvOp) and it.verb != "import" else (
            it if isinstance(it, str) else "")
        bad = unknown_builtins(text)
        if bad:
            raise _Unliftable(f"command substitution $({bad[0]} ...) is not a known function")
        from scbi.hooks.expand import ExpandError, check

        try:
            check(text)
        except ExpandError as e:
            raise _Unliftable(str(e)) from None


def lift_values(lines: list[str]) -> Values:
    items = _BodyLifter(lines, _value_item).run()
    _check_builtins(items)
    return Values(items)


def lift_env(lines: list[str]) -> EnvOps:
    ops = _BodyLifter(
        lines, _env_item, lambda local, n, v: EnvOp("local" if local else "assign", (n, v))
    ).run()
    _check_builtins(ops)
    return EnvOps(ops)


# ------------------------------------------------------------------ main


def lift(trace: PluginTrace, names: set[str] | None = None) -> LiftResult:
    """Lift ``trace``; ``names`` is the namespace after loading the plug-in
    (inherited hooks included) used to check variant compositions. Command
    hooks and functions are converted to the command language
    (scbi.plugin.liftcmd)."""
    plugin = trace.name
    pdef = PluginDef(plugin, variables=dict(trace.variables))
    res = LiftResult(pdef)

    #  Top-level code other than function definitions, inherit-plugin /
    #  with-variant calls and assignments (or output when sourced) has no
    #  YAML form: the plug-in stays a Bash one
    if trace.has_code or trace.output:
        res.issues.append(Issue("top-level", "code at the top level of the plug-in (not only definitions)"))

    defined_before: dict[str, str] = {}

    for call in trace.calls:
        defined_before.update(call.functions)
        if call.name == "inherit-plugin":
            o = parse_inherit_args(plugin, call.args)
            pdef.inherits.append(
                Inherit(
                    o.parent,
                    tuple(h for h in re.split(r"[|,]", o.hooks) if h),
                    tuple(h for h in re.split(r"[|,]", o.custom_hooks) if h),
                    o.no_variant,
                    o.name,
                )
            )
        elif call.name == "with-variant":
            vname, args = call.args[0], call.args[1:]
            packages = args[: args.index("--env")] if "--env" in args else args
            env_lines = args[args.index("--env") + 1 :] if "--env" in args else []
            try:
                env = lift_env(env_lines).ops
            except _Unliftable as e:
                res.issues.append(Issue(f"with-variant {vname}", str(e)))
                env = ()
            pdef.os_variants.append(
                OsVariant(vname, tuple("" if p.upper() == "NONE" else p for p in packages), env)
            )
            #  own functions defined before with-variant are overwritten
            for name in defined_before:
                if name.startswith(f"{plugin}-{vname}-") and trace.functions.get(name) == defined_before[name]:
                    res.issues.append(Issue(name, "defined before with-variant, overwritten by it"))

    #  Hooks only calling the same hook of other variants, e.g.
    #  c-darktable-all-depends calling c-darktable-{ai,hdr,jxl}-depends
    composite: dict[str, list[str]] = {}  # function -> called functions

    for name, definition in trace.functions.items():
        key = parse_hook_name(plugin, name)
        lines = body_lines(definition)
        params, rest = split_params(lines)
        calls = _variant_calls(plugin, key, rest)
        if calls:
            composite[name] = calls
            continue
        try:
            if key is None:
                for pos, (_, n) in enumerate(params):
                    if n != pos + 1:
                        raise _Unliftable(f"parameters not in order: {params}")
                script = _lift_cmd(rest, {n: p for p, n in params})
                pdef.functions[name] = Function(tuple(p for p, _ in params), script)
                continue

            spec = catalog.spec(key.hook)
            for pname, n in params:
                if n > len(spec.params) or spec.params[n - 1] != pname:
                    raise _Unliftable(
                        f"parameter {pname}=${n} does not match the hook signature "
                        f"({' '.join(spec.params) or 'no parameter'})"
                    )
            if spec.kind == COMMAND:
                pdef.hooks[key] = Commands(_lift_cmd(rest, {i + 1: p for i, p in enumerate(spec.params)}))
            elif spec.kind == VALUE:
                pdef.hooks[key] = lift_values(rest)
            else:
                pdef.hooks[key] = lift_env(rest)
        except _Unliftable as e:
            res.issues.append(Issue(name, str(e)))

    if composite:
        res.composite = composite
        _variants_from_composite(trace, pdef, composite, res, names)
    return res


def _lift_cmd(lines: list[str], params: dict[int, str]) -> str:
    from scbi.plugin.liftcmd import CmdUnliftable, lift_commands

    try:
        return lift_commands(lines, params).rstrip("\n")
    except CmdUnliftable as e:
        raise _Unliftable(str(e)) from None


def _variant_calls(plugin: str, key: HookKey | None, lines: list[str]) -> list[str]:
    """Functions called when the body only calls the same hook of other
    variants (with or without arguments), else []."""
    if key is None or key.qualifier in (PLAIN, "common", "default"):
        return []
    calls = []
    for ln in lines:
        name = ln.split()[0] if ln.split() else ""
        k = parse_hook_name(plugin, name)
        if (k is None or k.hook != key.hook or k.cross != key.cross
                or k.qualifier in (PLAIN, "common", "default", key.qualifier)):
            return []
        calls.append(name)
    return calls


class _AliasNamespace:
    def __init__(self, names: set[str], aliases: dict[str, tuple[str, ...]], plugin: str):
        self.names, self.aliases, self.plugin = names, aliases, plugin

    def fn_exists(self, name: str) -> bool:
        return name in self.names

    def variant_members(self, module: str, variant: str) -> tuple[str, ...]:
        return self.aliases.get(variant, ()) if module == self.plugin else ()


class _LegacyNamespace:
    def __init__(self, names: set[str]):
        self.names = names

    def fn_exists(self, name: str) -> bool:
        return name in self.names


def _variants_from_composite(trace, pdef, composite, res, names) -> None:
    """Turn composite hooks into ``variants:`` and check the equivalence."""
    from scbi.plugin.resolve import get_hook, variant_hooks

    plugin = trace.name
    aliases: dict[str, list[str]] = {}
    for fname, calls in composite.items():
        q = parse_hook_name(plugin, fname).qualifier
        members = aliases.setdefault(q, [])
        for c in calls:
            m = parse_hook_name(plugin, c).qualifier
            if m not in members:
                members.append(m)

    legacy_names = set(names) if names is not None else set(trace.functions)
    new_names = legacy_names - set(composite)
    legacy_ns = _LegacyNamespace(legacy_names)
    new_ns = _AliasNamespace(new_names, {q: tuple(m) for q, m in aliases.items()}, plugin)

    def effective(functions: list[str]) -> list[str]:
        out: list[str] = []
        for f in functions:
            for g in composite.get(f, [f]):
                if g and g not in out:
                    out.append(g)
        return out

    for q, members in aliases.items():
        for variant in [q] + [f"{q}.{m}" for m in members] + [f"{m}.{q}" for m in members]:
            for hook in catalog.step_names():
                for cross in (False, True):
                    #  compare with the selection rule used by the driver
                    if catalog.spec(hook).cumulative:
                        old = effective(variant_hooks(legacy_ns, plugin, hook, variant, cross))
                        #  duplicates aside: with "variants:" a variant
                        #  selected twice calls its hook once
                        new = effective(variant_hooks(new_ns, plugin, hook, variant, cross))
                    else:
                        old = effective([get_hook(legacy_ns, plugin, variant, hook, cross)])
                        new = [x for x in [get_hook(new_ns, plugin, variant, hook, cross)] if x]
                    if old != new:
                        res.issues.append(Issue(
                            f"{plugin}-{q}-*",
                            f"variant {q} cannot be expressed as variants: {{{q}: [{', '.join(members)}]}}"
                            f" (hook {hook}, variant {variant}{', cross' if cross else ''}:"
                            f" {old} != {new})",
                        ))
                        return
        pdef.variants[q] = tuple(members)

