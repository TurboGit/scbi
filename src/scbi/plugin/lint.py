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
from dataclasses import dataclass

import yaml

from scbi.plugin import catalog, yamlfmt
from scbi.plugin.model import EnvOp, EnvOps, Guarded, Commands, LocalAssign, Values

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    level: str
    where: str  # the hook (or section) concerned
    message: str


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

        #  a meta-module (modules, no sources) is not built: out-of-tree
        #  has no use
        if "modules" in data and "out-of-tree" in data and not ({"vcs", "archive"} & set(map(str, data))):
            self.warning("out-of-tree", "not used by a meta-module (no sources)")

        fpdef = header.get("functions")
        if fpdef is not None:
            for fname, f in fpdef.functions.items():
                known = set(f.params) | set(ALL_PARAMS)
                self.check_shell(f"function {fname}", f.script, known, other_params=False)
        return self.issues

    def _env_defined(self) -> set[str]:
        """Variables set by the environment actions of the plug-in."""
        names: set[str] = set()

        def walk(items) -> None:
            for it in items:
                if isinstance(it, Guarded):
                    walk(it.items)
                elif isinstance(it, EnvOp) and it.args and it.verb not in ("import", "mkdir"):
                    nm = _NAME.match(it.args[0])
                    if nm:
                        names.add(nm.group(0))

        for key in ("env", "build-env", "tests-env"):
            if key in self.data:
                try:
                    pdef = yamlfmt.from_data(self.name, {key: self.data[key]}, self.name)
                except yamlfmt.FormatError:
                    continue
                for body in pdef.hooks.values():
                    if isinstance(body, EnvOps):
                        walk(body.ops)
        return names

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
        text = _strip_single_quotes(script)
        self.check_names(label, referenced(text), known, assigned(text), other_params, hook)
        for line in _bad_log_levels(script):
            self.error(label, f"line {line}: log: level must be an integer >= 1")

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
    try:
        data = yaml.load(text, Loader=yamlfmt._Loader) or {}
    except yaml.YAMLError as e:
        return [Issue(ERROR, "yaml", " ".join(str(e).split()))]
    if not isinstance(data, dict):
        return [Issue(ERROR, "yaml", "a mapping is expected")]
    return Linter(name, data, where or name, known).run()
