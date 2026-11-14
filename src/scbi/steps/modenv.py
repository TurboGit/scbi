"""Environment of a module build: port of ``handle-env``,
``handle-build-depends-env``, ``handle-tests-depends-env``,
``handle-module-env`` (driver, hooks/compat.sh) and of
``plugin-call-env-hooks`` / ``plugin-call-variant-hooks`` (0_runtime).

The environment actions of the plug-in definitions are applied by Python
(scbi.env, so a ``define_var`` of the Python environment file sees each
of them); the env hooks of legacy Bash plug-ins still run in a hook shell
until legacy loading is removed. When a function of the ``define-var``
family is redefined in Bash (runtime, plug-in), every env hook runs in a
hook shell (scbi.hooks.policy), as before.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from scbi.bashcompat import words
from scbi.env import ACTIONS, Environment
from scbi.errors import Exit
from scbi.hooks.evaluate import apply_env
from scbi.hooks.exec import env_code
from scbi.hooks.policy import python_env_allowed
from scbi.plugin import catalog
from scbi.plugin.model import EnvOps
from scbi.plugin.resolve import variant_hooks
from scbi.walker import Walker

#  Runtime and driver functions ported here: a redefinition (e.g. by a
#  plug-in) makes the driver run the Bash ones
PORTED_FUNCTIONS = ("plugin-call-env-hooks", "plugin-call-variant-hooks", "is-meta-module",
                    "is-meta-aggregate-module")


def python_allowed(builder) -> bool:
    return all(builder.ported(name) for name in PORTED_FUNCTIONS)


class _Recording(Environment):
    """``define-var`` replaced by a recorder: the actions are given to
    ``recorder`` and only the SET ones applied (a following hook sees the
    value)."""

    recorder = None

    def define_var(self, action: str, var: str, value: str = "") -> None:
        self.recorder(action, var, value)
        if ACTIONS.get(action) == "SET":
            self.export(var, value)


#  The recording define-var of the Bash hooks (legacy plug-ins)
_BASH_RECORDER = ("function define-var() {{ printf '%s\\0%s\\0%s\\0' \"$1\" \"$2\" \"$3\" >> {file}\n"
                  "  [[ $1 == SET || $1 == S ]] && export \"$2=$3\"; true; }}\n")


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
            self.python_env = True
        else:
            self.env = env if env is not None else Environment(d.sv)
            rec = self.env.vars.values.get("SCBI_ENV_MODULE", "")
            self.env.record = Path(rec) if rec else None
            self.python_env = python_env_allowed(d.runtime.functions, d.sv.functions, d.registry.functions)
        self.walker = Walker(builder)
        #  output of the legacy hooks (None: the console)
        self.out = None

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
                           out=None) -> None:
        """``plugin-call-variant-hooks PLUGIN HOOK PREFIX TARGET VARIANT``
        for an environment hook: each selected hook applied to the
        environment, in order."""
        d = self.d
        cross = d.runner().cross
        args = [prefix, target, variant]
        for fct in variant_hooks(d.registry, plugin, hook, variant, cross):
            obj = d.registry.functions.get(fct)
            ctx = self.b.ctx(plugin, variant, hook)
            ctx.env = self.env
            ctx.arrays = {"SCBI_MODULES_DIR": self.b.modules_dir}
            ctx.target_dir = self.b.target_dir
            if isinstance(obj, EnvOps) and self.python_env:
                ctx.params = dict(zip(catalog.spec(hook).params, args))
                apply_env(obj, ctx, d.base_env())
            else:
                #  legacy hook (or define-var redefined): $H $PREFIX $TARGET $VARIANT
                self._bash_hook(ctx, fct, args, out)

    def _bash_hook(self, ctx, fct: str, args: list[str], out) -> None:
        code = " ".join([fct, *[_q(a) for a in args]])
        rec = None
        if self.recorder is not None:
            fd, rec = tempfile.mkstemp()
            os.close(fd)
            code = _BASH_RECORDER.format(file=_q(rec)) + code + " > /dev/null 2>&1"
        try:
            _, arr = env_code(self.b.shell(), ctx, code, ["SCBI_MODULES_DIR"],
                              out or self.out or self.b.out)
            if rec is not None:
                items = Path(rec).read_text(errors="surrogateescape").split("\0")
                for i in range(0, len(items) - 2, 3):
                    self.recorder(*items[i:i + 3])
        finally:
            if rec is not None:
                os.unlink(rec)
        if "SCBI_MODULES_DIR" in arr:
            self.b.modules_dir = arr["SCBI_MODULES_DIR"]

    def call_env_hooks(self, formodule: str, modref: str, hook: str, out=None) -> None:
        """Port of ``plugin-call-env-hooks FORMODULE MODREF ENV``."""
        module, variant, _kind, ref = self.module_info(modref, formodule)
        if ref == "skip":
            return
        mode = "default"
        if self.is_meta_module(modref):
            mode = self.walker.aggregate_mode(modref) or mode
        tvdir = self.b.target_dir(module, variant)
        target, prefix = self.d.get("SCBI_TARGET"), self.d.get("SCBI_PREFIX")
        if mode in ("direct", "recursive"):
            mods = words("\n".join(self.d.runner().variant_values(
                module, variant, "modules", [prefix, target, variant], self.d.plan, self.b.modules_list)))
            for mod in mods:
                if mode == "direct":
                    self.call_variant_hooks(mod, hook, f"{tvdir}/install", target, variant, out)
                else:
                    def do_set_env(argv: list[str]) -> None:
                        a = argv + [""] * 2
                        emodule, evariant = self.module_info(a[1], a[0])[:2]
                        self.call_variant_hooks(emodule, hook, f"{tvdir}/install", target, evariant, out)
                    self.walker.walk("for-all-modules-depends-with-meta", do_set_env, mod, name="do-set-env")
        else:
            self.call_variant_hooks(module, hook, f"{tvdir}/install", target, variant, out)

    def module_env(self, formodule: str, modref: str, hook: str, out=None) -> None:
        """Port of ``handle-module-env FORMODULE MODREF ENV``."""
        module, variant, _kind, ref = self.module_info(modref, formodule)
        if ref == "skip":
            return
        self._record(f"\n# {modref}\n")
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
        recording file with ``record``). ``out``: the output of the legacy
        hooks (default: the console)."""
        rc = 0
        self.out = out
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


def _q(s: str) -> str:
    from scbi.hooks.exec import quote

    return quote(s)
