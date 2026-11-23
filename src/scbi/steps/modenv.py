"""Environment of a module build: port of ``handle-env``,
``handle-build-depends-env``, ``handle-tests-depends-env``,
``handle-module-env`` (driver, hooks/compat.sh) and of
``plugin-call-env-hooks`` / ``plugin-call-variant-hooks`` (0_runtime).

The environment actions of the plug-in definitions are applied by Python
(scbi.env): the ``define-var`` function of the environment file sees each of
them.
"""

from __future__ import annotations

from pathlib import Path

from scbi.bashcompat import words
from scbi.env import ACTIONS, Environment
from scbi.errors import Exit
from scbi.hooks.evaluate import apply_env, set_plugin_vars
from scbi.plugin import catalog
from scbi.plugin.model import EnvOps
from scbi.plugin.resolve import variant_hooks
from scbi.walker import Walker

class _Recording(Environment):
    """``define-var`` replaced by a recorder: the actions are given to
    ``recorder`` and only the SET ones applied (a following hook sees the
    value)."""

    recorder = None

    def define_var(self, action: str, var: str, value: str = "") -> None:
        self.recorder(action, var, value)
        if ACTIONS.get(action) == "SET":
            self.export(var, value)


class ModuleEnv:
    """The environment actions applied to ``env`` (default: the driver
    variables). Changes made by an ``import`` action may replace
    ``env.vars``: the caller gets the result from ``self.env.vars``.

    With ``recorder``, the actions are not applied but given to
    ``recorder(action, var, value)`` (SET ones applied), on a copy of the
    driver variables."""

    def __init__(self, builder, env: Environment | None = None, recorder=None):
        self.b = builder
        self.d = builder.d
        d = self.d
        self.recorder = recorder
        if recorder is not None:
            sv = env.vars if env is not None else d.sv
            self.env = _Recording(sv.copy())
            self.env.recorder = recorder
        else:
            self.env = env if env is not None else Environment(d.sv)
            rec = self.env.vars.values.get("SCBI_ENV_MODULE", "")
            self.env.record = Path(rec) if rec else None
        self.walker = Walker(builder)

    # ------------------------------------------------------------ helpers

    def module_info(self, modref: str, formodule: str | None = None) -> list[str]:
        return self.walker.module_info(modref, formodule)

    def is_meta_module(self, modref: str) -> bool:
        """Port of ``is-meta-module``."""
        module, variant = self.module_info(modref)[:2]
        reg = self.d.registry
        if not reg.loaded.get(module):
            self.walker.load_module(modref)
        return reg.loaded.get(f"{module}.{variant}") == "meta"

    def _record(self, text: str) -> None:
        if self.env.record is not None:
            with open(self.env.record, "a") as f:
                f.write(text)

    # ------------------------------------------------------------ hooks

    def call_variant_hooks(self, plugin: str, hook: str, prefix: str, target: str, variant: str,
                           out=None, host: bool = False) -> None:
        """``plugin-call-variant-hooks PLUGIN HOOK PREFIX TARGET VARIANT``
        for an environment hook: each selected hook applied to the
        environment, in order. ``host``: the hooks of the build for the
        host (a host@ dependency in a cross build)."""
        d = self.d
        cross = d.runner().cross and not host
        args = [prefix, target, variant]
        for fct in variant_hooks(d.registry, plugin, hook, variant, cross):
            obj = d.registry.functions.get(fct)
            ctx = self.b.ctx(plugin, variant, hook)
            if host:
                ctx.target = ctx.host
            ctx.env = self.env
            ctx.arrays = {"SCBI_MODULES_DIR": self.b.modules_dir}
            ctx.target_dir = self.b.target_dir
            if not isinstance(obj, EnvOps):
                raise TypeError(f"{fct}: not an environment hook")
            ctx.params = dict(zip(catalog.spec(hook).params, args))
            set_plugin_vars(ctx, d.registry.plugin_variables(plugin))
            apply_env(obj, ctx, d.base_env())

    def call_env_hooks(self, formodule: str, modref: str, hook: str, out=None, host: bool = False) -> None:
        """Port of ``plugin-call-env-hooks FORMODULE MODREF ENV``. ``host``:
        the hooks of the build for the host (a host@ dependency in a cross
        build), an aggregate meta-module giving the ones of its modules."""
        module, variant, _kind, ref = self.module_info(modref, formodule)
        if ref == "skip":
            return
        mode = "default"
        if self.is_meta_module(modref):
            mode = self.walker.aggregate_mode(modref) or mode
        if host:
            tvdir = self.b.host_dir(module, variant)
            target = self.d.get("SCBI_HOST")
        else:
            tvdir = self.b.target_dir(module, variant)
            target = self.d.get("SCBI_TARGET")
        prefix = self.d.get("SCBI_PREFIX")
        if mode in ("direct", "recursive"):
            mods = words("\n".join(self.d.runner().variant_values(
                module, variant, "modules", [prefix, target, variant], self.d.plan, self.b.modules_list)))
            for mod in mods:
                if host and not self.d.registry.loaded.get(mod):
                    #  the modules of a host@ meta-module are not walked
                    self.walker.load_module(mod)
                if mode == "direct":
                    self.call_variant_hooks(mod, hook, f"{tvdir}/install", target, variant, out, host=host)
                else:
                    def do_set_env(argv: list[str]) -> None:
                        a = argv + [""] * 2
                        emodule, evariant = self.module_info(a[1], a[0])[:2]
                        self.call_variant_hooks(emodule, hook, f"{tvdir}/install", target, evariant, out,
                                                host=host)
                    self.walker.walk("for-all-modules-depends-with-meta", do_set_env, mod, name="do-set-env")
        else:
            self.call_variant_hooks(module, hook, f"{tvdir}/install", target, variant, out, host=host)

    def module_env(self, formodule: str, modref: str, hook: str, out=None) -> None:
        """Port of ``handle-module-env FORMODULE MODREF ENV``."""
        module, variant, _kind, ref = self.module_info(modref, formodule)
        if ref == "skip":
            return
        self._record(f"\n# {modref}\n")
        if self.b.is_host_dep(modref):
            #  the build for the host: its directories, its native hooks
            hvdir = self.b.host_dir(module, variant)
            builddir = "src" if self.d.get("SCBI_ISOOT") == "false" else "build"
            self.b.modules_dir[module] = f"{hvdir}/install"
            self.b.modules_dir[f"{module}@src"] = f"{hvdir}/src"
            self.b.modules_dir[f"{module}@build"] = f"{hvdir}/{builddir}"
            self.call_env_hooks(formodule, modref, hook, out, host=True)
            return
        tvdir = self.b.target_dir(module, variant)
        builddir = "src" if self.d.get("SCBI_ISOOT") == "false" else "build"
        self.b.modules_dir[module] = f"{tvdir}/install"
        self.b.modules_dir[f"{module}@src"] = f"{tvdir}/src"
        self.b.modules_dir[f"{module}@build"] = f"{tvdir}/{builddir}"
        self.call_env_hooks(formodule, modref, hook, out)

    # ------------------------------------------------------------ walks

    def _callback(self, argv: list[str]) -> None:
        """``handle-env-callback``."""
        a = argv + [""] * 7
        formodule, modref, level, depends_kind, _ext, _meta, is_aggregated = a[:7]
        if is_aggregated == "true":
            return
        if _int(level) >= 1 or depends_kind == "tests" or self.is_meta_module(formodule):
            self.module_env(formodule, modref, "env")

    def _walk(self, entry: str, modref: str) -> int:
        return self.walker.walk(entry, self._callback, modref, name="handle-env-callback")

    def handle_env(self, formodule: str, modref: str) -> int:
        return self._walk("for-all-modules-depends-with-meta", modref)

    def handle_build_depends_env(self, formodule: str, modref: str) -> int:
        return self._walk("for-all-modules-build-depends-with-meta", modref)

    def handle_tests_depends_env(self, formodule: str, modref: str) -> int:
        return self._walk("for-all-modules-tests-depends-with-meta", modref)

    def run(self, calls, out=None) -> int:
        """Run a sequence of ``(name, formodule, modref[, hook[, "record"]])``
        calls as the driver code does (lines of a Bash script: an ``exit``,
        e.g. recursive dependencies, stops them); returns the status of the
        last one, or the exit status. ``name`` is a handle-*-env function
        or ``module-env`` (handle-module-env, its output appended to the
        recording file with ``record``)."""
        rc = 0
        try:
            for name, *args in calls:
                if name == "module-env":
                    hout = out
                    if args[-1] == "record":
                        args = args[:-1]
                        hout = self._append_record
                    self.module_env(*args, out=hout)
                    rc = 0
                else:
                    rc = getattr(self, name.replace("-", "_"))(*args)
        except Exit as e:
            return e.status
        return rc

    def _append_record(self, line: str) -> None:
        self._record(line + "\n")


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0

