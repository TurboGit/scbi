"""Running of a module step: port of ``module-variant-wrapper``,
``_internal_module-variant-wrapper`` and ``module-wrapper`` of the
driver, and of ``show-command`` (scripts.d/2_log).

For each step the wrapper displays the starting/cached/completed or
failure messages, chooses the directory (the build directory, the
sources for an in-tree build, the module directory for setup and
wrapup), writes the reproduction file ``<step>.cmd`` and runs the hook,
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

from scbi.bashenv import quote
from scbi.hooks.exec import is_nop, run_code
from scbi.plugin import formats
from scbi.plugin.resolve import get_hook
from scbi.steps import interp

#  driver functions reproduced here (a user definition makes them run in
#  Bash) and ported runtime functions
DRIVER_FUNCTIONS = ("module-wrapper", "module-variant-wrapper", "_internal_module-variant-wrapper")
PORTED_FUNCTIONS = ("show-command", "_internal_copy-plugin")

_REPRODUCE = re.compile(r".*(config|build|install|cross-config|cross-build|cross-install)$")
_HOME_DIR_STEP = re.compile(r"(pre-|post-)*(setup|wrapup)$")
_TRACE = re.compile(r"^_[_]*TRACE: ")


def python_allowed(builder) -> bool:
    """The steps may be run by the Python wrapper."""
    d = builder.d
    for name in DRIVER_FUNCTIONS:
        if name in d.sv.functions or name in d.registry.functions:
            return False
    return all(builder.ported(name) for name in PORTED_FUNCTIONS)


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
        commands = interp.is_commands(b, fct)
        if commands:
            tests_opts = self.get("SCBI_TESTS_OPTIONS") if is_tests else self.get("TESTS_OPTS")
            hook = interp.Hook(b, module, variant, fct, [prefix, target, variant, tests_opts], cwd)
            hook.write_replay(clog)
            #  the plug-in files, as show-command copies them
            copy_plugin(self.get("SCBI_PLUGINS"), module, f"{tvdir}/logs", [], self.d.registry)
        else:
            self.write_command(clog, fct, prefix, cwd)

        if not is_tests and cached:
            return 0

        dlog = self.get("SCBI_DLOG") == "yes" or is_tests
        if dlog:
            sink = _Sink([(log, "a"), (mlog, "w")], console=True)
        else:
            sink = _Sink([(mlog, "w"), (log, "a")], console=False)
        sys.stdout.flush()
        if commands:
            res = hook.run(sink.text, trace=None if dlog else sink.line)
        elif dlog:
            tests_opts = self.get("SCBI_TESTS_OPTIONS") if is_tests else self.get("TESTS_OPTS")
            res = self.run_hook(fct, [prefix, target, variant, tests_opts], cwd, sink.line, trace=False)
        else:
            res = self.run_hook(fct, [prefix, target, variant], cwd, sink.line, trace=True)

        if res != 0:
            if self.get("SCBI_DLOG") == "on-failure" and step != "tests":
                self.tail(mlog)
            b.elog(module, mstep, "failed", "with", "error", str(res))
            if _REPRODUCE.match(step):
                b.elog(module, "to", "reproduce:")
                if commands:
                    b.elog(module, "scbi", "replay", clog)
                    b.elog(module, "use", "--trace", "option", "for", "debug")
                else:
                    b.elog(module, "bash", clog)
                    b.elog(module, "use", "bash", "-x", "option", "for", "debug")
            return res
        b.ilog(module, f"{mstep}{dvariant}", "completed")
        return 0

    def run_hook(self, fct: str, args: list[str], cwd: str, on_line, trace: bool) -> int:
        """Run the hook function in a hook shell from ``cwd`` (xtrace in the
        logs when ``trace``)."""
        b = self.b
        call = " ".join([fct, *(quote(a) for a in args)])
        if trace:
            code = (f'{{\n    PS4="_TRACE: "\n    set -o xtrace\n    {call}\n    res=$?\n'
                    "    set +o xtrace\n    exit $res\n} 2>&1")
        else:
            code = f"{call} 2>&1"
        sys.stdout.flush()
        ctx = b.ctx(self.module, self.variant, fct[len(self.module) + 1:])
        ctx.cwd = type(ctx.cwd)(cwd)
        return run_code(b.shell(), ctx, code, on_line).returncode

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

    # ---------------------------------------------------- show-command

    def write_command(self, clog: str, fct: str, prefix: str, cwd: str) -> None:
        """``show-command MODULE FCT PREFIX TARGET VARIANT &> $clog``: the
        Bash script reproducing the step."""
        module, variant = self.module, self.variant
        tvdir = self.b.target_dir(module, variant)
        lines = [f"# {fct}", "(", f"   cd {cwd}", f"   source {self.get('SCBI_BDIR')}/.scbi.runtime",
                 f"   LOGDIR={tvdir}/logs", "   [[ -f $LOGDIR/env.cmd ]] && source $LOGDIR/env.cmd"]
        if self.get("SCBI_TARGET") != self.get("SCBI_HOST"):
            lines.append("   target-env $SCBI_BDIR/install $SCBI_TARGET")
        lines += ["   [[ -f $LOGDIR/build-plan ]] &&", "      load-runtime-module-plan $LOGDIR/build-plan", ""]
        #  the errors of _internal_copy-plugin go to the file too
        copy_plugin(self.get("SCBI_PLUGINS"), module, f"{tvdir}/logs", lines)
        lines += [f"   source $LOGDIR/{module}", "",
                  f"   {fct} {prefix} {self.get('SCBI_TARGET')} {variant}", ")"]
        try:
            with open(clog, "w") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            sys.stderr.write(f"{clog}: {e.strerror}\n")


def copy_plugin(plugins: str, plugin: str, dest: str, errors: list[str], registry=None) -> None:
    """``_internal_copy-plugin PLG DIR``: the plug-in file and the files of
    the plug-ins it inherits are copied to DIR (with ``registry``: the
    definition files too, scbi.plugin.formats)."""
    definition = formats.find(Path(plugins), plugin) if registry is not None else None
    if definition is not None:
        try:
            shutil.copy(definition, dest)
        except OSError as e:
            errors.append(f"cp: cannot create regular file '{dest}': {e.strerror}")
        pdef = registry.definitions.get(plugin)
        for inh in (pdef.inherits if pdef else ()):
            copy_plugin(plugins, inh.parent, dest, errors, registry)
    src = f"{plugins}/{plugin}"
    if not os.path.isfile(src):
        return
    try:
        shutil.copy(src, dest)
    except OSError as e:
        errors.append(f"cp: cannot create regular file '{dest}': {e.strerror}")
        return
    with open(f"{dest}/{plugin}", errors="surrogateescape") as f:
        text = f.read()
    for line in text.split("\n"):
        words = line.split()
        if not words or words[0] != "inherit-plugin":
            continue
        #  getopt -l no-variant,hooks:,custom-hooks:,name: -- inherit-plugin ...
        #  (the first word is taken as the short options): the first
        #  argument which is not an option is the inherited plug-in
        args, parent = words[1:], ""
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("--hooks", "--custom-hooks", "--name"):
                i += 2
                continue
            if a == "--no-variant" or re.match(r"--(hooks|custom-hooks|name)=", a):
                i += 1
                continue
            if a == "--":
                parent = args[i + 1] if i + 1 < len(args) else ""
                break
            parent = a
            break
        if parent:
            copy_plugin(plugins, parent, dest, errors, registry)


def _append(path: str, text: str) -> None:
    try:
        with open(path, "a") as f:
            f.write(text)
    except OSError:
        pass
