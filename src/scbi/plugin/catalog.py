"""Catalog of the hooks known to SCBI.

For each hook: its parameters (the signature is a property of the hook, not
of each plug-in), its kind and how the driver selects the implementations
among the variants:

- ``cumulative``: all matching hooks are called (``plugin-call-variant-hooks``):
  the ``common`` one, then each selected variant, or the plain one when no
  variant hook exists.
- otherwise the first matching hook is used (``get-hook``).

Sources: SCBI_ALL_HOOKS (scripts.d/0_runtime), call sites in the scbi driver
and runtime, doc/scbi.tex section "Hooks".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#  Canonical order (SCBI_ALL_HOOKS, also used by scbi-format)
ALL_HOOKS = (
    "plan", "vcs", "archive", "patches", "source-tree", "version", "only-explicit-build",
    "out-of-tree", "modules", "aggregate", "propagate-version", "build-depends",
    "tests-depends", "depends", "external-env", "build-env", "tests-env", "env",
    "setup", "config-options", "config", "build", "install", "wrapup", "prefix",
    "tests", "run",
)

#  Kinds
COMMAND = "command"  # shell commands run in the build tree
VALUE = "value"  # output (one value per line) used by the driver
ENV = "env"  # sets environment variables

STD_PARAMS = ("PREFIX", "TARGET", "VARIANT")

#  Steps having pre-/post- hooks and generic module-<step> implementations
STEPS = ("setup", "config", "build", "install", "wrapup", "tests")


@dataclass(frozen=True)
class HookSpec:
    name: str
    kind: str
    params: tuple[str, ...] = STD_PARAMS
    cumulative: bool = False


_SPECS = [
    HookSpec("plan", VALUE, ("PLAN",)),
    HookSpec("vcs", VALUE, ()),
    HookSpec("archive", VALUE, ("VERSION",)),
    HookSpec("patches", VALUE, STD_PARAMS + ("KIND", "REF"), cumulative=True),
    #  entries (from, to, exclude): the sources of several modules combined
    HookSpec("source-tree", VALUE),
    HookSpec("version", COMMAND),
    HookSpec("only-explicit-build", VALUE),
    HookSpec("out-of-tree", VALUE),
    HookSpec("modules", VALUE, cumulative=True),
    HookSpec("aggregate", VALUE),
    HookSpec("propagate-version", VALUE),
    HookSpec("build-depends", VALUE, cumulative=True),
    HookSpec("tests-depends", VALUE, cumulative=True),
    HookSpec("depends", VALUE, cumulative=True),
    HookSpec("external-env", VALUE, cumulative=True),
    HookSpec("build-env", ENV, cumulative=True),
    HookSpec("tests-env", ENV, cumulative=True),
    HookSpec("env", ENV, cumulative=True),
    HookSpec("setup", COMMAND),
    HookSpec("config-options", VALUE, cumulative=True),
    HookSpec("config", COMMAND),
    HookSpec("build", COMMAND),
    HookSpec("install", COMMAND),
    HookSpec("wrapup", COMMAND),
    HookSpec("prefix", VALUE),
    #  OPTIONS: options given with --tests (SCBI_TESTS_OPTIONS)
    HookSpec("tests", COMMAND, STD_PARAMS + ("OPTIONS",)),
    #  run: functions called in sequence in a shell by "scbi shell --run"
    HookSpec("run", COMMAND, cumulative=True),
]

HOOKS: dict[str, HookSpec] = {s.name: s for s in _SPECS}
assert tuple(HOOKS) == ALL_HOOKS

#  What each hook is for (one sentence, from the doc, section "Hooks"):
#  the help of the editors (scbi schema)
DESCRIPTIONS = {
    "plan": "The name of the build plan of the meta-module.",
    "vcs": "The VCS of the module sources: proxy, options, protocol, url [, dir].",
    "archive": "The archive of the module sources: proxy, options, protocol, url, file [, dir].",
    "patches": "The patch files to apply (in $SCBI_PATCH); REF is the version of the module.",
    "source-tree": "The source tree of the build made of the sources of several modules, in order:"
                   " entries from (a dependency, or this plug-in: its name or none), to, exclude.",
    "version": "Prints the version of the installed module.",
    "only-explicit-build": "true: the module is only built when on the command line, not as a dependency"
                           " (default false).",
    "out-of-tree": "Whether the module is built out of its source tree (default true).",
    "modules": "The modules of the meta-module.",
    "aggregate": "direct or recursive: the installations of the modules are copied into the meta-module"
                 " (default no).",
    "propagate-version": "Whether the version and/or the variant of the meta-module are propagated to its"
                         " modules: version, variant, both or no (default version).",
    "build-depends": "The modules needed to build the module but not to use it (tools).",
    "tests-depends": "The modules needed to run the testsuite of the module.",
    "depends": "The modules needed to build and to use the module (os@-<name> for an OS package).",
    "external-env": "Values added to the build identifier: the module is rebuilt when they change.",
    "build-env": "The environment needed to build the module.",
    "tests-env": "The environment needed to run the testsuite of the module.",
    "env": "The environment needed to use the module: set for the modules depending on it.",
    "setup": "Puts the sources in place before the configuration (generally not needed).",
    "config-options": "The options of the configuration, given by $(config-options) in the config hook.",
    "config": "Configures the sources (configure, cmake...); the sources are in ../src.",
    "build": "Builds the module, generally with make.",
    "install": "Installs the module in $PREFIX, generally with make install.",
    "wrapup": "Whatever is needed after the installation.",
    "prefix": "The global install directory of the module: NONE skips the global installation.",
    "tests": "Runs the testsuite of the module (--tests).",
    "run": "The command line run by scbi shell --run without argument.",
    "plugin": "The name of the plug-in (optional): it must match the file name.",
    "inherit": "Plug-ins whose hooks are inherited: from, hooks, custom-hooks, no-variant, name.",
    "with-variants": "Variants using OS packages, with no build step: {<variant>: {packages: [...], env: [...]}}.",
    "vars": "Variables of the plug-in, {NAME: value} or {NAME: [values]} (a list), expanded in all its hooks.",
    "functions": "Functions callable from the command hooks: {name: {params: [A, B], run: <commands>}}.",
    "variants": "Variants including other variants: {all: [ai, hdr]}.",
}


def description(hook: str) -> str:
    """What a hook (or a header key) is for: pre-/post- steps and
    build-<target> included."""
    for prefix in ("pre-", "post-"):
        if hook.startswith(prefix) and hook[len(prefix):] in STEPS:
            return f"Run {'before' if prefix == 'pre-' else 'after'} the {hook[len(prefix):]} step."
    if is_build_target(hook):
        return f"The build step run for --build-target={hook[len('build-'):]}."
    return DESCRIPTIONS.get(hook, "")


#  User defined hook (environment file), called by the driver at the end
FINAL_STEP = HookSpec(
    "module-final-step",
    COMMAND,
    STD_PARAMS + ("MODULE", "DEPENDS_KIND", "IS_META", "IS_AGGREGATED", "IS_UP_TO_DATE"),
)


#  Canonical order of the keys of a YAML plug-in (scbi format and the
#  converter): header, sources, dependencies, environment, steps (each one
#  between its pre- and post- hooks), others, meta-modules
HEADER_KEYS = ("plugin", "inherit", "with-variants", "vars", "functions", "variants")
_ORDER = (
    "modules", "aggregate", "propagate-version", "plan",
    "vcs", "archive", "patches", "source-tree",
    "depends", "build-depends", "tests-depends",
    "env", "build-env", "tests-env", "external-env",
    "setup", "out-of-tree", "only-explicit-build", "config-options",
    "config", "build", "install", "wrapup", "tests",
    "run", "version", "prefix",
)


def _format_order() -> tuple[str, ...]:
    keys: list[str] = list(HEADER_KEYS)
    for h in _ORDER:
        if h in STEPS:
            keys += [f"pre-{h}", h, f"post-{h}"]
        else:
            keys.append(h)
    return tuple(keys)


FORMAT_ORDER = _format_order()


def step_names() -> list[str]:
    """All hook names a plug-in can define, including pre-/post- steps."""
    names = list(ALL_HOOKS)
    for s in STEPS:
        names += [f"pre-{s}", f"post-{s}"]
    return names


#  build-<target>: the build step run for --build-target=<target>
_BUILD_TARGET = re.compile(r"build-[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*")


def is_build_target(hook: str) -> bool:
    """``build-<target>`` (not an existing hook such as build-env; the
    target name does not contain ``build-``)."""
    return (bool(_BUILD_TARGET.fullmatch(hook)) and hook not in HOOKS
            and "build-" not in hook[len("build-"):])


def is_hook(name: str) -> bool:
    """A hook name a plug-in can define."""
    return name in step_names() or is_build_target(name)


def format_rank(hook: str) -> float:
    """Position of ``hook`` in the canonical order (FORMAT_ORDER), the
    build-<target> hooks just after build."""
    if is_build_target(hook):
        return FORMAT_ORDER.index("build") + 0.5
    return FORMAT_ORDER.index(hook) if hook in FORMAT_ORDER else len(FORMAT_ORDER)


def spec(hook: str) -> HookSpec:
    """Spec of ``hook``, pre-/post- step hooks and build-<target> share
    the step spec."""
    for prefix in ("pre-", "post-"):
        if hook.startswith(prefix) and hook[len(prefix):] in STEPS:
            return HOOKS[hook[len(prefix):]]
    if is_build_target(hook):
        return HOOKS["build"]
    return HOOKS[hook]


assert sorted(FORMAT_ORDER[len(HEADER_KEYS):]) == sorted(step_names())
