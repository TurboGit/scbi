"""The modules of a build, for scbi show --freeze, --json and --sbom: the
walk of the dependencies of the modules (meta-modules and OS packages
included) with their module reference resolved in the build plan, and the
source reference recorded in the sandbox by their last build."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from scbi.bashcompat import assoc_keys, words
from scbi.modref import is_host_prefixed, strip_host

#  the parent of a module of the command line
ROOT = "@root"


@dataclass
class Node:
    """A module of the build (or an OS package, ``external``)."""
    module: str
    variant: str = "default"
    kind: str = "NONE"
    ref: str = "NONE"
    #  the plug-ins depending on it, with the kind of dependency
    #  (default, build, tests, modules), ROOT for the command line
    parents: list[tuple[str, str]] = field(default_factory=list)
    external: bool = False
    meta: bool = False
    #  host@ dependency of a cross build (the build for the host)
    host: bool = False
    #  the key of the build plan giving its reference (module or
    #  <for-module>=module)
    plan_key: str = ""

    @property
    def keep(self) -> bool:
        return self.ref.startswith("keep:")

    @property
    def version(self) -> str:
        """The version of the reference (keep: removed)."""
        return self.ref[len("keep:"):] if self.keep else self.ref


@dataclass(frozen=True)
class SourceRef:
    """A line of the source-ref file of a module (handle-sources):
    ``<module> <origin> <ref> <id-kind> <id>``; origin is the VCS label
    (git, mercurial, subversion), archive or none."""
    origin: str
    ref: str
    id_kind: str
    id: str


def root_modules(driver) -> list[str]:
    """The modules of the command line or, without any, the modules of
    the build plan (not the @for, skipped nor kept entries)."""
    mods = words(" ".join(driver.modules))
    if mods:
        return mods
    plan = driver.plan
    return [m for m in assoc_keys(plan.modver)
            if "=" not in m and not m.endswith((".skip", ".keep")) and plan.modver.get(f"{m}.skip") != "yes"]


def walk(driver, builder, roots: list[str]) -> tuple[list[Node], int]:
    """The modules needed by ``roots`` (themselves included), the
    dependencies first; returns (nodes, status). The dependencies of the
    build (depends, build-depends, modules of meta-modules) are walked, not
    the ones of the testsuites."""
    from scbi.walker import Walker

    plan = driver.plan
    nodes: dict[str, Node] = {}
    order: list[str] = []
    #  the meta-modules: the parent of their modules (the walker gives the
    #  kind "default" to them)
    metas: set[str] = set()

    def add(key: str, node: Node) -> Node:
        if key not in nodes:
            nodes[key] = node
            order.append(key)
        return nodes[key]

    def callback(argv: list[str]) -> None:
        #  FORMODULE NAME... LEVEL DEPENDS_KIND IS_EXT IS_META IS_AGG: an
        #  external alias may expand to several package names
        if len(argv) < 6:
            return
        formodule, names = argv[0], argv[1:-5]
        depends_kind, is_ext, is_meta = argv[-4], argv[-3], argv[-2]
        parent = (formodule, "modules" if formodule in metas else depends_kind)
        if is_ext == "true":
            for name in names:
                node = add(f"os:{name}", Node(module=name, external=True))
                if parent not in node.parents:
                    node.parents.append(parent)
            return
        modref = " ".join(names)
        info = (plan.module_ref(strip_host(modref), formodule) + [""] * 4)[:4]
        module, variant, kind, ref = info
        fkey = f"{formodule}={module}"
        plan_key = fkey if plan.modver.get(fkey) else module
        host = builder.is_host_dep(modref) if is_host_prefixed(modref) else False
        key = ("host@" if host else "") + plan_key
        node = add(key, Node(module=module, variant=variant, kind=kind, ref=ref, host=host,
                             meta=is_meta == "true", plan_key=plan_key))
        if node.meta:
            metas.add(module)
        if parent not in node.parents:
            node.parents.append(parent)

    status = 0
    for modref in roots:
        #  the modules of a meta-module are walked before it: it must be
        #  known as a meta-module first
        _mark_metas(driver, builder, modref, metas)
        res = Walker(builder).walk("for-all-modules-with-meta-ext", callback, modref,
                                   name="planwalk-callback")
        if res != 0:
            status = 1
    return [nodes[k] for k in order], status


def _mark_metas(driver, builder, modref: str, metas: set[str]) -> None:
    """The meta-modules among the modules of the build (needed before the
    walk reaches their modules)."""
    from scbi.walker import Walker

    def callback(argv: list[str]) -> None:
        if len(argv) >= 6 and argv[-3] == "false" and argv[-2] == "true":
            info = (driver.plan.module_ref(strip_host(" ".join(argv[1:-5])), argv[0]) + [""])
            metas.add(info[0])

    #  -ext: the OS packages are listed, not checked (a missing one would
    #  stop the walk)
    Walker(builder).walk("for-all-modules-with-meta-ext", callback, modref, name="planwalk-meta-callback")


def source_ref(driver, module: str) -> SourceRef | None:
    """The source reference of the last build of ``module`` in the
    sandbox (None when not built, or without sources: a meta-module)."""
    path = os.path.join(driver.get("SCBI_BDIR"), module, "source-ref")
    try:
        with open(path, errors="surrogateescape") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        f = line.split()
        #  a meta-module aggregating others has their lines, not its own
        if len(f) >= 3 and f[0] == module:
            return SourceRef(f[1], f[2], f[3] if len(f) > 3 else "", " ".join(f[4:]))
    return None


def format_ref(module: str, variant: str, kind: str, ref: str) -> str:
    """``module[/variant][:version]`` (# for an archive version)."""
    text = module
    if variant and variant != "default":
        text += f"/{variant}"
    if ref and ref != "NONE":
        text += f":#{ref}" if kind == "VERSION" else f":{ref}"
    return text
