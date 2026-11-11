"""In-memory plug-in model: the function namespace of the loaded plug-ins.

In the Bash driver all plug-ins are sourced in the same shell: a hook
exists when a function named ``<plugin>[-<variant>][-cross]-<hook>`` is
defined, inheritance copies functions under a new name and ``with-variant``
defines functions. The Python model reproduces this with a single
namespace (function name -> definition) per registry, filled when plug-ins
are loaded, never written back to the plug-in files.

Ports of ``load-module`` (file loading part), ``_inherit-plugin_internal``,
``inherit-plugin``, ``with-variant`` and ``copy-function``
(scripts.d/0_runtime).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scbi.plugin.catalog import ALL_HOOKS
from scbi.plugin.legacy import Call, PluginTrace, trace_plugin

ALL_HOOKS_RE = "|".join(ALL_HOOKS)


class PluginError(Exception):
    pass


def copy_function(definition: str, new_name: str) -> str:
    """Port of ``copy-function``: same body under another name."""
    return f"{new_name} ({definition.split('(', 1)[1]}"


@dataclass
class InheritOptions:
    parent: str
    no_variant: bool = False
    hooks: str = ""  # "a|b" as built by inherit-plugin
    custom_hooks: str = ""
    name: str | None = None


_LONG_OPTS = {"no-variant": False, "hooks": True, "custom-hooks": True, "name": True}


def parse_inherit_args(plugin: str, args: list[str]) -> InheritOptions:
    """Arguments of ``inherit-plugin`` as parsed by GNU getopt.

    Options may follow the plug-in name (getopt permutes arguments) and
    long options may be abbreviated when unambiguous.
    """
    opts: list[tuple[str, str]] = []
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional += args[i + 1 :]
            break
        if a.startswith("--"):
            key, _, value = a[2:].partition("=")
            matches = [o for o in _LONG_OPTS if o == key] or [
                o for o in _LONG_OPTS if o.startswith(key)
            ]
            if len(matches) != 1:
                raise PluginError(f"unknown option {a} in {plugin}")
            opt = matches[0]
            if _LONG_OPTS[opt] and "=" not in a:
                i += 1
                value = args[i] if i < len(args) else ""
            opts.append((opt, value))
        else:
            positional.append(a)
        i += 1

    res = InheritOptions(parent=positional[0] if positional else "")
    hooks: list[str] = []
    custom: list[str] = []
    for opt, value in opts:
        if opt == "no-variant":
            res.no_variant = True
        elif opt == "hooks":
            hooks.append(value)
        elif opt == "custom-hooks":
            custom.append(value)
        elif opt == "name":
            res.name = value
    res.hooks = "|".join(hooks)
    res.custom_hooks = "|".join(custom)
    return res


def with_variant_functions(plugin: str, vname: str, args: list[str]) -> dict[str, str]:
    """Functions defined by ``with-variant <vname> <args>`` (port)."""
    funcs: dict[str, str] = {}

    def define(suffix: str, body: str) -> None:
        name = f"{plugin}-{vname}-{suffix}"
        funcs[name] = f"function {name}() {body}"

    for h in ("config", "build", "install"):
        for s in (h, f"pre-{h}", f"post-{h}", f"cross-{h}", f"cross-pre-{h}", f"cross-post-{h}"):
            define(s, "{ true; }")
    for h in ("env", "build-env", "build-depends", "patches"):
        for s in (h, f"common-{h}", f"default-{h}", f"cross-{h}", f"common-cross-{h}", f"default-cross-{h}"):
            define(s, "{ true; }")
    define("vcs", "{ echo NONE; echo NONE; echo NONE; echo NONE; }")
    define("archive", "{ echo NONE; echo NONE; echo NONE; echo NONE; echo NONE; }")
    define("prefix", "{ echo NONE; }")

    #  depends, and env after --env
    hook, body, prefix = "depends", "{ ", "echo "
    for a in args:
        if a == "--env":
            define(hook, f"{body} true; }}")
            hook, body, prefix = "env", "{ ", ""
        elif a.upper() == "NONE":
            body += f" {prefix};"
        else:
            body += f" {prefix}{a};"
    define(hook, f"{body} true; }}")
    return funcs


@dataclass
class Registry:
    """Plug-ins loaded from ``plugins_dir`` and their function namespace."""

    plugins_dir: Path
    module_alias: dict[str, str] = field(default_factory=dict)
    tracer: Callable[[Path], PluginTrace] = trace_plugin

    functions: dict[str, str] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    loaded: dict[str, str] = field(default_factory=dict)  # SCBI_LOADED[module]
    inherits: dict[str, list[str]] = field(default_factory=dict)  # SCBI_LOADED[P.inh]
    traces: dict[str, PluginTrace] = field(default_factory=dict)

    # --------------------------------------------------------------- loading

    def load_module(self, module: str) -> bool:
        """Port of the plug-in loading part of ``load-module``.

        Returns False when the plug-in (or its alias) cannot be found.
        """
        if self.loaded.get(module):
            return True
        path = self.plugins_dir / module
        if path.is_file():
            self._source(module, path)
            self.loaded[module] = "yes"
            return True
        alias = self.module_alias.get(module)
        if alias:
            if (self.plugins_dir / alias).is_file():
                self._inherit(False, ALL_HOOKS_RE, alias, module)
                return True
        return False

    def _source(self, module: str, path: Path) -> None:
        trace = self.traces.get(module)
        if trace is None:
            trace = self.tracer(path)
            self.traces[module] = trace

        previous: dict[str, str] = {}

        def define_new(snapshot: dict[str, str]) -> None:
            #  functions (re)defined by the plug-in since the previous call
            for name, definition in snapshot.items():
                if previous.get(name) != definition:
                    self.functions[name] = definition

        for call in trace.calls:
            define_new(call.functions)
            previous = call.functions
            self._apply(module, call)
        define_new(trace.functions)
        self.variables.update(trace.variables)

    def _apply(self, plugin: str, call: Call) -> None:
        if call.name == "inherit-plugin":
            opts = parse_inherit_args(plugin, call.args)
            hooks = opts.hooks or ALL_HOOKS_RE
            if opts.custom_hooks:
                hooks += "|" + opts.custom_hooks
            self.inherits.setdefault(plugin, []).append(opts.parent)
            self._inherit(opts.no_variant, hooks.replace(",", "|"), opts.parent, opts.name or plugin)
        elif call.name == "with-variant":
            if not call.args:
                raise PluginError(f"with-variant without variant name in {plugin}")
            self.functions.update(with_variant_functions(plugin, call.args[0], call.args[1:]))

    def _inherit(self, no_variant: bool, hooks: str, parent: str, plugin: str) -> None:
        """Port of ``_inherit-plugin_internal``."""
        self.load_module(parent)

        regexp = f"({hooks})$"
        if no_variant:
            regexp = f"^{parent}(-pre|-post|-cross)*-({hooks})$"
        pattern = re.compile(regexp)

        #  compgen -A function "$HPLUGIN-": sorted names with this prefix
        for hook in sorted(n for n in self.functions if n.startswith(f"{parent}-")):
            if pattern.search(hook):
                new = hook.replace(parent, plugin, 1)
                #  Only copy if new function does not exists
                if new not in self.functions:
                    self.functions[new] = copy_function(self.functions[hook], new)

    # ------------------------------------------------------------- queries

    def fn_exists(self, name: str) -> bool:
        return name in self.functions
