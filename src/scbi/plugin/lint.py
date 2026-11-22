"""Checks of a YAML plug-in (scbi lint).

All the problems are reported, not only the first one: each section and
each hook (each qualifier of a hook) is validated on its own with the
loader (scbi.plugin.yamlfmt), plus checks the loader does not do.

Errors: unknown keys (typos), invalid structure or values, guards,
built-ins, environment actions. Warnings: empty hooks and variables not
known in a hook (not a parameter of the hook, not set by the plug-in or
the hook itself, not a driver or a usual environment variable).
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from dataclasses import dataclass

import yaml

from scbi.plugin import catalog, yamlfmt
from scbi.plugin.model import EnvOp, EnvOps, Guarded, Commands, LocalAssign, SourceEntry, Values

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    level: str
    where: str  # the hook (or section) concerned
    message: str
    #  position in the file (1-based, 0: unknown): scbi.plugin.lintpos
    line: int = 0
    column: int = 0


#  Values expected for some single-value hooks
CHOICES = {
    "out-of-tree": ("true", "false"),
    "only-explicit-build": ("true", "false"),
    "aggregate": ("direct", "recursive", "no"),
    #  false: documented to disable the propagation, works as no
    "propagate-version": ("version", "variant", "both", "no", "false"),
}

#  Variables usual in a build environment, never reported
STANDARD_VARS = frozenset("""
PATH HOME PWD OLDPWD USER LOGNAME SHELL LANG LANGUAGE LC_ALL LC_CTYPE TMPDIR TERM
HOSTNAME HOSTTYPE OSTYPE MACHTYPE UID EUID IFS RANDOM SECONDS LINENO FUNCNAME
BASH BASH_SOURCE BASH_VERSION BASH_REMATCH PIPESTATUS REPLY OPTARG OPTIND
CC CXX CPP FC LD AR AS NM RANLIB STRIP CFLAGS CXXFLAGS CPPFLAGS FFLAGS LDFLAGS LIBS
MAKE MAKEFLAGS DESTDIR PKG_CONFIG PKG_CONFIG_PATH LD_LIBRARY_PATH LIBRARY_PATH
C_INCLUDE_PATH CPLUS_INCLUDE_PATH CPATH PYTHONPATH PYTHONHOME PERL5LIB
GPR_PROJECT_PATH ADA_PROJECT_PATH ADA_INCLUDE_PATH ADA_OBJECTS_PATH
CMAKE_PREFIX_PATH ACLOCAL_PATH MANPATH INFOPATH XDG_DATA_DIRS JAVA_HOME
""".split())

#  Driver variables visible in the hooks (besides SCBI_*)
DRIVER_VARS = frozenset("log module variant VERSION_OK VERSION_ERROR".split())

_REF = re.compile(r"\$(?:\{[#!]?)?([A-Za-z_][A-Za-z0-9_]*)")
_ASSIGN = re.compile(r"(?:^|[\s;&|(`])([A-Za-z_][A-Za-z0-9_]*)(?:\[[^\]]*\])?\+?=")
_DECL = re.compile(r"(?:^|[\s;&|(])(?:local|export|declare|readonly|typeset)((?:\s+-\w+)*)\s+([^;&|\n]*)")
_READ = re.compile(r"(?:^|[\s;&|(])read((?:\s+-[A-Za-z]+)*)\s+([A-Za-z_][A-Za-z0-9_ \t]*)")
_FOR = re.compile(r"(?:^|[\s;&|(])(?:for|select)\s+((?:[A-Za-z_][A-Za-z0-9_]*\s+)+)in\b")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*")
#  command language: VAR = value, export VAR = value
_CMD_ASSIGN = re.compile(r"(?m)^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+=(?:\s|$)")


def _strip_single_quotes(script: str) -> str:
    """The script without single-quoted strings and comments (no expansion
    there)."""
    out, i, n = [], 0, len(script)
    in_dq = False
    while i < n:
        c = script[i]
        if c == "\\" and i + 1 < n:
            out.append(script[i:i + 2])
            i += 2
            continue
        if c == '"':
            in_dq = not in_dq
        elif c == "'" and not in_dq:
            j = script.find("'", i + 1)
            i = n if j < 0 else j + 1
            out.append("''")
            continue
        elif c == "#" and not in_dq and (i == 0 or script[i - 1] in " \t\n;"):
            j = script.find("\n", i)
            i = n if j < 0 else j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def referenced(text: str) -> list[str]:
    """Variables expanded in shell text (``$NAME``, ``${NAME...}``), in
    order, without duplicates; ``\\$`` is not an expansion."""
    names: list[str] = []
    for m in _REF.finditer(text):
        start = m.start()
        backslashes = 0
        while start - backslashes - 1 >= 0 and text[start - backslashes - 1] == "\\":
            backslashes += 1
        if backslashes % 2:
            continue
        if m.group(1) not in names:
            names.append(m.group(1))
    return names


def assigned(script: str) -> set[str]:
    """Variables set by a body (command language: ``VAR = ...``, ``export
    VAR = ...``, ``for NAME in ...:``, ``NAME=value`` words; and the shell
    forms: local/export/declare, read)."""
    names = {m.group(1) for m in _ASSIGN.finditer(script)}
    names.update(m.group(1) for m in _CMD_ASSIGN.finditer(script))
    for m in _DECL.finditer(script):
        for word in m.group(2).split():
            nm = _NAME.match(word)
            if nm:
                names.add(nm.group(0))
    for m in _READ.finditer(script):
        names.update(m.group(2).split())
    names.update(n for m in _FOR.finditer(script) for n in m.group(1).split())
    return names


def _all_params() -> dict[str, list[str]]:
    """Parameter -> hooks having it."""
    result: dict[str, list[str]] = {}
    for spec in catalog.HOOKS.values():
        for p in spec.params:
            if spec.name not in result.setdefault(p, []):
                result[p].append(spec.name)
    return result


ALL_PARAMS = _all_params()


class Linter:
    def __init__(self, name: str, data: dict, where: str, known: frozenset[str] = frozenset()):
        self.name = name
        self.data = data
        self.where = where
        self.issues: list[Issue] = []
        self.plugin_vars: set[str] = set()
        self.function_refs: set[str] = set()
        #  the variables of the environment (settings of the environment
        #  file, passthrough variables): known in every hook
        self.known = known

    def error(self, where: str, msg: str) -> None:
        self.issues.append(Issue(ERROR, where, msg))

    def warning(self, where: str, msg: str) -> None:
        self.issues.append(Issue(WARNING, where, msg))

    def load(self, section: dict):
        """The loader on a part of the plug-in; its error reported."""
        try:
            return yamlfmt.from_data(self.name, section, self.name)
        except yamlfmt.FormatError as e:
            msg = str(e)
            prefix = f"{self.name}: " if msg.startswith(f"{self.name}: ") else ""
            first = msg[len(prefix):]
            where, _, text = first.partition(": ")
            if where.startswith(f"{self.name}."):
                where = where[len(self.name) + 1:]
            self.error(where if text else "plugin", text or first)
            return None

    # ------------------------------------------------------------ checks

    def run(self) -> list[Issue]:
        data = self.data
        if "plugin" in data and str(data["plugin"]) != self.name:
            self.error("plugin", f"plugin name {data['plugin']!r} does not match the file name {self.name!r}")

        header = {}
        for key in catalog.HEADER_KEYS:
            if key in data and key != "plugin":
                pdef = self.load({key: data[key]})
                header[key] = pdef
        fpdef = header.get("functions")
        #  the variables read by the functions of the plug-in
        self.function_refs: set[str] = set()
        for f in (fpdef.functions.values() if fpdef is not None else ()):
            self.function_refs.update(referenced(f.script))
        self.plugin_vars = set(str(k) for k in (data.get("vars") or {}))
        self.plugin_vars |= self._env_defined()

        names = catalog.step_names()
        for key, value in data.items():
            key = str(key)
            if key in yamlfmt.RESERVED:
                continue
            if not catalog.is_hook(key):
                close = difflib.get_close_matches(key, names + list(yamlfmt.RESERVED), n=1)
                hint = f", did you mean {close[0]!r}?" if close else ""
                self.error(key, f"unknown hook {key!r}{hint}")
                continue
            self.check_hook(key, value)

        if "source-tree" in data:
            self.check_source_tree()

        #  a meta-module (modules, no sources) is not built: out-of-tree
        #  has no use
        if "modules" in data and "out-of-tree" in data and not ({"vcs", "archive"} & set(map(str, data))):
            self.warning("out-of-tree", "not used by a meta-module (no sources)")

        if fpdef is not None:
            for fname, f in fpdef.functions.items():
                known = set(f.params) | set(ALL_PARAMS)
                self.check_shell(f"function {fname}", f.script, known, other_params=False)
        return self.issues

    def check_source_tree(self) -> None:
        """source-tree: each from a dependency (depends, build-depends, any
        qualifier), no two entries with the same target, no entry replaced
        by a later one, the sources of the module used."""
        def entries(items):
            for it in items:
                if isinstance(it, Guarded):
                    yield from entries(it.items)
                elif isinstance(it, SourceEntry):
                    yield it

        try:
            tree = yamlfmt.from_data(self.name, {"source-tree": self.data["source-tree"]}, self.name)
        except yamlfmt.FormatError:
            return  # reported by check_hook
        deps: set[str] = set()
        for key in ("depends", "build-depends"):
            if key not in self.data:
                continue
            try:
                pdef = yamlfmt.from_data(self.name, {key: self.data[key]}, self.name)
            except yamlfmt.FormatError:
                continue
            for body in pdef.hooks.values():
                for text in _texts(body.items if isinstance(body, Values) else ()):
                    for w in text.split():
                        deps.add(re.split(r"[/:]", w, maxsplit=1)[0])
        own = False
        for key, body in tree.hooks.items():
            label = "source-tree" + (".cross" if key.cross else "") + (f".{key.qualifier}" if key.qualifier else "")
            found = list(entries(body.items))
            own = own or any(not e.from_ for e in found)
            for e in found:
                if e.from_ and "$" not in e.from_ and e.from_ not in deps:
                    self.error(label, f"{e.from_} is not a dependency (depends, build-depends)")
            targets = [e.to for e in found]
            for to in sorted({t for t in targets if targets.count(t) > 1}):
                self.error(label, f"several entries copied to {to}")
            for i, e in enumerate(found):
                for later in found[i + 1:]:
                    if later.to != e.to and (later.to == "." or e.to.startswith(f"{later.to}/")):
                        self.warning(label, f"the entry of {e.from_ or 'the module'} ({e.to}) is replaced by"
                                     f" the later entry of {later.from_ or 'the module'} ({later.to})")
                        break
        if not own and ("vcs" in self.data or "archive" in self.data):
            self.warning("source-tree", "no entry for the sources of the module (an entry without from): unused")

    def _env_defined(self) -> set[str]:
        """Variables set by the environment actions of the plug-in."""
        return env_vars(self.name, self.data, ("env", "build-env", "tests-env"))

    def check_hook(self, hook: str, value) -> None:
        """Each qualifier on its own, then the content of the bodies."""
        if yamlfmt._is_qualifier_map(hook, value):
            parts = []
            for q, body in value.items():
                if str(q) == yamlfmt.CROSS_KEY and yamlfmt._is_qualifier_map(hook, body):
                    for q2, body2 in body.items():
                        parts.append((f"{hook}.cross.{q2}", {hook: {"cross": {q2: body2}}}))
                else:
                    parts.append((f"{hook}.{q}", {hook: {q: body}}))
        else:
            parts = [(hook, {hook: value})]
        #  the local variables (NAME = ...) of the hook, known by all its
        #  items
        self.hook_locals: set[str] = set()
        for _, section in parts:
            try:
                pdef = yamlfmt.from_data(self.name, section, self.name)
            except yamlfmt.FormatError:
                continue
            for body in pdef.hooks.values():
                if isinstance(body, (Values, EnvOps)):
                    items = body.items if isinstance(body, Values) else body.ops
                    self.hook_locals |= {a.name for a in _locals(items)}
        #  the items of a list one by one: an error does not hide the next
        #  ones
        expanded = []
        for label, section in parts:
            body, path = _leaf(section, hook)
            if isinstance(body, list) and len(body) > 1:
                expanded += [(label, _replace_leaf(section, hook, path, [item])) for item in body]
            else:
                expanded.append((label, section))
        for label, section in expanded:
            pdef = self.load(section)
            if pdef is None:
                continue
            for body in pdef.hooks.values():
                self.check_body(hook, label, body)

    def check_body(self, hook: str, label: str, body) -> None:
        spec = catalog.spec(hook)
        known = set(spec.params)
        if isinstance(body, Commands):
            if not body.script.strip():
                self.warning(label, "defined but empty")
                return
            self.check_shell(label, body.script, known, other_params=True, hook=hook)
            return
        items = body.items if isinstance(body, Values) else body.ops
        if not items:
            self.warning(label, "defined but empty")
            return
        if isinstance(body, Values) and hook in CHOICES:
            for it in items:
                if isinstance(it, str) and "$" not in it and it.lower() not in CHOICES[hook]:
                    self.error(label, f"{it!r} is not one of {'/'.join(CHOICES[hook])}")
        local = {a.name for a in _locals(items)} | getattr(self, "hook_locals", set())
        for text in _texts(items):
            self.check_names(label, referenced(text), known, local, other_params=True, hook=hook)

    def check_shell(self, label: str, script: str, known: set[str], other_params: bool,
                    hook: str = "") -> None:
        script = _write_blocks(script)
        text = _strip_single_quotes(script)
        self.check_names(label, referenced(text), known, assigned(text), other_params, hook)
        for line in _bad_log_levels(script):
            self.error(label, f"line {line}: log: level must be an integer >= 1")
        #  a variable set and never read (the functions of the plug-in see
        #  the variables of their caller: one read there counts)
        used = set(referenced(script)) | self.function_refs
        for line, name in _unused_assignments(script, used):
            self.warning(label, f"line {line}: variable {name} is set but never used")

    def check_names(self, label: str, names: list[str], known: set[str], local: set[str],
                    other_params: bool, hook: str = "") -> None:
        for name in names:
            if (name in known or name in local or name in self.plugin_vars or name.startswith("SCBI_")
                    or name in STANDARD_VARS or name in DRIVER_VARS or name in self.known):
                continue
            if other_params and name in ALL_PARAMS:
                hooks = ", ".join(ALL_PARAMS[name])
                self.warning(label, f"{name} is a parameter of {hooks}, not of {hook}")
            else:
                self.warning(label, f"variable {name} is not known in this hook")


def _unused_assignments(script: str, used: set[str]) -> list[tuple[int, str]]:
    """(line, name) of the first assignment (``NAME = ...``, not
    exported) of each variable of a body never read (``$NAME`` nowhere in
    ``used``); none for a body with a syntax error (reported elsewhere)."""
    from scbi.hooks import cmdlang

    try:
        body = cmdlang.parse(script, 1)
    except cmdlang.CmdSyntaxError:
        return []
    found: dict[str, int] = {}

    def walk(steps) -> None:
        for step in steps or ():
            if isinstance(step, cmdlang.Assign):
                if not step.export and step.name not in used:
                    found.setdefault(step.name, step.line)
            elif isinstance(step, cmdlang.If):
                for _, b in step.branches:
                    walk(b)
                walk(step.orelse)
            elif isinstance(step, cmdlang.For):
                walk(step.body)

    walk(body)
    return [(line, name) for name, line in found.items()]


_WRITE = re.compile(r"^(\s*)(write|append|write-raw|append-raw)\s+.+:\s*$")


def _write_blocks(script: str) -> str:
    """The body with the text of its write blocks as the linter sees it:
    nothing in a raw block (write-raw, append-raw: no expansion), the
    quotes of the other ones made blanks (literal there, as in a
    here-document: not the start of a quoted string). The lines are kept
    (the line numbers of the messages)."""
    lines = script.split("\n")
    out: list[str] = []
    block: tuple[int, bool] | None = None  # indentation of the header, raw
    for line in lines:
        indent = len(line) - len(line.lstrip())
        if block is not None and (not line.strip() or indent > block[0]):
            out.append("" if block[1] else line.replace("'", " ").replace('"', " "))
            continue
        block = None
        m = _WRITE.match(line)
        if m:
            block = (len(m.group(1)), m.group(2).endswith("-raw"))
        out.append(line)
    return "\n".join(out)


def _bad_log_levels(script: str) -> list[int]:
    """The lines of the ``log`` commands whose level, given literally, is
    not an integer >= 1 (a syntax error of the body is reported
    elsewhere)."""
    from scbi.hooks import cmdlang

    try:
        body = cmdlang.parse(script, 1)
    except cmdlang.CmdSyntaxError:
        return []
    lines: list[int] = []

    def walk(steps) -> None:
        for step in steps or ():
            if isinstance(step, cmdlang.AndOr):
                for pipeline in (step.first, *(p for _, p in step.rest)):
                    for cmd in pipeline.commands:
                        texts = [cmdlang._word_text(w) for w in cmd.words]
                        if texts[:1] == ["log"]:
                            level = texts[1] if len(texts) > 1 else ""
                            if "$" not in level and not (level.isdigit() and int(level) >= 1):
                                lines.append(step.line)
            elif isinstance(step, cmdlang.If):
                for _, b in step.branches:
                    walk(b)
                walk(step.orelse)
            elif isinstance(step, cmdlang.For):
                walk(step.body)

    walk(body)
    return lines


def env_vars(name: str, data: dict, keys) -> set[str]:
    """Variables set by the environment actions of the hooks ``keys`` of
    a plug-in (all qualifiers, guarded actions included; for ``env``, the
    environment of the with-variants too)."""
    names: set[str] = set()

    def walk(items) -> None:
        for it in items:
            if isinstance(it, Guarded):
                walk(it.items)
            elif isinstance(it, EnvOp) and it.args and it.verb not in ("import", "mkdir"):
                nm = _NAME.match(it.args[0])
                if nm:
                    names.add(nm.group(0))

    for key in keys:
        if key in data:
            try:
                pdef = yamlfmt.from_data(name, {key: data[key]}, name)
            except yamlfmt.FormatError:
                continue
            for body in pdef.hooks.values():
                if isinstance(body, EnvOps):
                    walk(body.ops)
    #  the environment of the with-variants (native...) is the env of
    #  the module for that variant
    if "env" in keys and "with-variants" in data:
        try:
            pdef = yamlfmt.from_data(name, {"with-variants": data["with-variants"]}, name)
        except yamlfmt.FormatError:
            return names
        for wv in pdef.with_variants:
            walk(wv.env)
    return names


_DEP_HOOKS = ("depends", "build-depends", "tests-depends", "modules")


def _related(name: str, data: dict) -> tuple[list[str], list[str]]:
    """The dependencies (modules of the dependency hooks, all qualifiers,
    guarded items included; os@- packages and computed names left out)
    and the inherited plug-ins of a plug-in."""
    deps: list[str] = []

    def walk(items) -> None:
        for it in items:
            if isinstance(it, Guarded):
                walk(it.items)
            elif isinstance(it, str):
                for w in it.split():
                    if "$" not in w and not w.startswith("os@-"):
                        deps.append(re.split(r"[/:@]", w, maxsplit=1)[0])

    for key in _DEP_HOOKS:
        if key in data:
            try:
                pdef = yamlfmt.from_data(name, {key: data[key]}, name)
            except yamlfmt.FormatError:
                continue
            for body in pdef.hooks.values():
                if isinstance(body, Values):
                    walk(body.items)
    parents: list[str] = []
    if "inherit" in data:
        try:
            parents = [i.parent for i in yamlfmt.from_data(name, {"inherit": data["inherit"]}, name).inherits]
        except yamlfmt.FormatError:
            pass
    return [d for d in deps if d], parents


def dependency_vars(name: str, data: dict, find) -> frozenset[str]:
    """The variables a plug-in gets from the plug-ins it uses: the ``env``
    hooks of its dependencies (recursively, the modules of the
    meta-modules included) and, for its parents (inherit), their variables
    and environment hooks. ``find(name)``: the YAML file of a plug-in, or
    None. A union over all the variants: unknown files are ignored."""
    known: set[str] = set()
    seen: set[str] = {name}

    def load(n: str):
        path = find(n)
        if path is None:
            return None
        try:
            d = yaml.load(Path(path).read_text(errors="replace"), Loader=yamlfmt._Loader)
        except (OSError, yaml.YAMLError):
            return None
        return d if isinstance(d, dict) else None

    #  (plug-in, its data, kind): "dep" gives its env hook, "parent" all
    todo: list[tuple[str, dict, str]] = [(name, data, "self")]
    while todo:
        n, d, kind = todo.pop()
        if kind == "dep":
            known |= env_vars(n, d, ("env",))
        elif kind == "parent":
            known |= {str(k) for k in (d.get("vars") or {})}
            known |= env_vars(n, d, ("env", "build-env", "tests-env"))
        deps, parents = _related(n, d)
        for m, k in [(p, "parent" if kind in ("self", "parent") else "dep") for p in parents] + \
                [(m, "dep") for m in deps]:
            if m in seen:
                continue
            seen.add(m)
            md = load(m)
            if md is not None:
                todo.append((m, md, k))
    return frozenset(known)


def _leaf(section: dict, hook: str):
    """The body in a one-hook section and the keys leading to it."""
    value, path = section[hook], []
    while isinstance(value, dict) and len(value) == 1 and yamlfmt._is_qualifier_map(hook, value):
        (k, value), = value.items()
        path.append(k)
    return value, path


def _replace_leaf(section: dict, hook: str, path: list, body) -> dict:
    if not path:
        return {hook: body}
    inner: object = body
    for k in reversed(path):
        inner = {k: inner}
    return {hook: inner}


def _texts(items) -> list[str]:
    out: list[str] = []
    for it in items:
        if isinstance(it, Guarded):
            out += _texts(it.items)
        elif isinstance(it, EnvOp):
            out += [a for a in it.args if it.verb != "import"] or []
            if it.verb == "import" and it.args:
                out.append(it.args[0])
        elif isinstance(it, LocalAssign):
            out.append(it.text)
        elif isinstance(it, SourceEntry):
            out += [it.from_, it.to, *it.exclude]
        elif isinstance(it, str):
            out.append(it)
    return out


def _locals(items) -> list[LocalAssign]:
    out: list[LocalAssign] = []
    for it in items:
        if isinstance(it, Guarded):
            out += _locals(it.items)
        elif isinstance(it, LocalAssign):
            out.append(it)
    return out


def lint_text(name: str, text: str, where: str = "", known: frozenset[str] = frozenset()) -> list[Issue]:
    """The issues of the YAML plug-in ``name`` (its text); ``known``: the
    variables of the environment (settings of the environment file...)."""
    from scbi.plugin.lintpos import locate

    try:
        data = yaml.load(text, Loader=yamlfmt._Loader) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
        line, column = (mark.line + 1, mark.column + 1) if mark is not None else (1, 1)
        return [Issue(ERROR, "yaml", " ".join(str(e).split()), line, column)]
    if not isinstance(data, dict):
        return [Issue(ERROR, "yaml", "a mapping is expected", 1, 1)]
    return locate(text, Linter(name, data, where or name, known).run())
