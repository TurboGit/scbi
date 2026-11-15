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
    "plan", "vcs", "archive", "patches", "version", "only-explicit-build",
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

#  User defined hook (environment file), called by the driver at the end
FINAL_STEP = HookSpec(
    "module-final-step",
    COMMAND,
    STD_PARAMS + ("MODULE", "DEPENDS_KIND", "IS_META", "IS_AGGREGATED", "IS_UP_TO_DATE"),
)


#  Canonical order of the keys of a YAML plug-in (scbi format and the
#  converter): header, sources, dependencies, environment, steps (each one
#  between its pre- and post- hooks), others, meta-modules
HEADER_KEYS = ("plugin", "inherit", "vars", "functions", "variants", "with-variants")
_ORDER = (
    "vcs", "archive", "patches",
    "depends", "build-depends", "tests-depends",
    "env", "build-env", "tests-env", "external-env",
    "setup", "out-of-tree", "only-explicit-build", "config-options",
    "config", "build", "install", "wrapup", "tests",
    "run", "version", "prefix",
    "modules", "aggregate", "propagate-version", "plan",
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
