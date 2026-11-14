"""Running of a module step: port of ``module-variant-wrapper``,
``_internal_module-variant-wrapper`` and ``module-wrapper`` of the
driver.

For each step the wrapper displays the starting/cached/completed or
failure messages, chooses the directory (the build directory, the
sources for an in-tree build, the module directory for setup and
wrapup), writes the replay file ``<step>.cmd`` (scbi replay) and runs
the hook (command language, scbi.steps.interp),
its output going to the global log of the step, to the local log
``$TVDIR/logs/<step>.log`` and, with ``SCBI_DLOG=yes`` or for the tests,
to the console.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections import deque
from pathlib import Path

from scbi.plugin import formats
from scbi.plugin.model import Commands
from scbi.plugin.resolve import get_hook
from scbi.steps import interp

_REPRODUCE = re.compile(r".*(config|build|install|cross-config|cross-build|cross-install)$")
_HOME_DIR_STEP = re.compile(r"(pre-|post-)*(setup|wrapup)$")
_TRACE = re.compile(r"^_[_]*TRACE: ")


def is_nop(obj) -> bool:
    """A hook doing nothing (``true``): the step is skipped."""
    return isinstance(obj, Commands) and obj.is_nop()


class _Sink:
    """The destinations of the output of a step."""

    def __init__(self, files: list[tuple[str, str]], console: bool):
        self.paths = []
        for path, mode in files:
            try:
                open(path, mode).close()
                self.paths.append(path)
            except OSError as e:
                sys.stderr.write(f"tee: {path}: {e.strerror}\n")
        self.console = console

    def line(self, text: str) -> None:
        self.text(text + "\n")

    def text(self, text: str) -> None:
        if self.console:
            sys.stdout.write(text)
            sys.stdout.flush()
        for path in self.paths:
            with open(path, "a", errors="surrogateescape") as f:
                f.write(text)


class StepWrapper:
    def __init__(self, builder, module: str, variant: str):
        self.b = builder
        self.d = builder.d
        self.module = module
        self.variant = variant

    def get(self, name: str) -> str:
        return self.d.get(name)

    # ------------------------------------------------------------ entries

    def variant_step(self, prefix: str, step: str) -> int:
        """``module-variant-wrapper PREFIX MODULE VARIANT STEP``."""
        d = self.d
        fct = get_hook(d.registry, self.module, self.variant, step, d.runner().cross)
        return self.internal(prefix, fct)

    def internal(self, prefix: str, fct: str) -> int:
        """``_internal_module-variant-wrapper PREFIX MODULE VARIANT FCT``:
        nothing for a nop hook, 1 when the step fails."""
        if not fct or is_nop(self.d.registry.functions.get(fct)):
            return 0
        return 0 if self.wrapper(prefix, fct[len(self.module) + 1:]) == 0 else 1

    # ------------------------------------------------------------ wrapper

    def wrapper(self, prefix: str, step: str) -> int:
        """``module-wrapper PREFIX MODULE VARIANT STEP``: the status of the
        step."""
        module, variant = self.module, self.variant
        b = self.b
        dvariant = ""
        if variant not in step and variant != "default":
            dvariant = f" [{variant.replace('.', ' ')}]"
        mstep = step
        if step == "build" and self.get("BUILD_SCBI_TARGET"):
            mstep = f"build-{self.get('BUILD_SCBI_TARGET')}"

        log = f"{self.get('SCBI_LOGS')}/{self.get('TODAY')}/{self.get('SCBI_TARGET')}-{module}-{variant}-{mstep}.log"
        tvdir = b.target_dir(module, variant)
        mlog = f"{tvdir}/logs/{mstep}.log"
        clog = f"{tvdir}/logs/{mstep}.cmd"
        cached = b.fn_exists(f"{module}-cached")

        msg = "cached" if cached and mstep != "tests" else "starting"
        b.ilog(module, f"{mstep}{dvariant}", msg)

        bdir = self.get("SCBI_BDIR")
        mdir = f"{bdir}/{module}"
        builddir = "src" if self.get("SCBI_ISOOT") == "false" else "build"
        if _HOME_DIR_STEP.search(step):
            cwd = mdir
        elif os.path.isdir(f"{tvdir}/{builddir}"):
            cwd = f"{tvdir}/{builddir}"
        else:
            #  a native module has no sources for example
            cwd = mdir
        if not os.path.isdir(cwd):
            _append(log, f"cd: {cwd}: No such file or directory\n")
            cwd = os.getcwd()

        fct = f"{module}-{mstep}"
        target = self.get("SCBI_TARGET")
        is_tests = "tests" in step
        tests_opts = self.get("SCBI_TESTS_OPTIONS") if is_tests else self.get("TESTS_OPTS")
        hook = interp.Hook(b, module, variant, fct, [prefix, target, variant, tests_opts], cwd)
        hook.write_replay(clog)
        #  the plug-in files (and those of the inherited plug-ins)
        copy_plugin(self.get("SCBI_PLUGINS"), module, f"{tvdir}/logs", [], self.d.registry)

        if not is_tests and cached:
            return 0

        dlog = self.get("SCBI_DLOG") == "yes" or is_tests
        if dlog:
            sink = _Sink([(log, "a"), (mlog, "w")], console=True)
        else:
            sink = _Sink([(mlog, "w"), (log, "a")], console=False)
        sys.stdout.flush()
        res = hook.run(sink.text, trace=None if dlog else sink.line)

        if res != 0:
            if self.get("SCBI_DLOG") == "on-failure" and step != "tests":
                self.tail(mlog)
            b.elog(module, mstep, "failed", "with", "error", str(res))
            if _REPRODUCE.match(step):
                b.elog(module, "to", "reproduce:")
                b.elog(module, "scbi", "replay", clog)
                b.elog(module, "use", "--trace", "option", "for", "debug")
            return res
        b.ilog(module, f"{mstep}{dvariant}", "completed")
        return 0

    def tail(self, mlog: str) -> None:
        """``tail -100 $mlog | grep -v "^_[_]*TRACE: "``."""
        try:
            with open(mlog, errors="replace") as f:
                lines = deque(f, maxlen=100)
        except OSError:
            return
        for line in lines:
            if not _TRACE.match(line):
                sys.stdout.write(line if line.endswith("\n") else line + "\n")
        sys.stdout.flush()


def copy_plugin(plugins: str, plugin: str, dest: str, errors: list[str], registry) -> None:
    """The definition file of the plug-in and those of the plug-ins it
    inherits are copied to DIR (``_internal_copy-plugin`` of the Bash
    driver)."""
    definition = formats.find(Path(plugins), plugin)
    if definition is not None:
        try:
            shutil.copy(definition, dest)
        except OSError as e:
            errors.append(f"cp: cannot create regular file '{dest}': {e.strerror}")
    pdef = registry.definitions.get(plugin)
    for inh in (pdef.inherits if pdef else ()):
        copy_plugin(plugins, inh.parent, dest, errors, registry)


def _append(path: str, text: str) -> None:
    try:
        with open(path, "a") as f:
            f.write(text)
    except OSError:
        pass
