"""scbi show --freeze: the build plan of the modules with every reference
pinned to the sources of their last build (a lock file).

A Git module is pinned to the commit built, an archive to its version;
the references that cannot be pinned (Mercurial, Subversion, users'
checkouts, modules not built or built from another reference) are kept
as they are, with a comment saying why.
"""

from __future__ import annotations

import sys
import time

from scbi.bashcompat import assoc_keys
from scbi.sources.data import display_ref
from scbi.tools.planwalk import Node, format_ref, root_modules, source_ref, walk

#  the VCS whose module reference can be a commit (git-branch accepts a
#  SHA-1; hg-branch and svn-branch only branches and tags)
PINNABLE_VCS = ("git",)


def pin(driver, node: Node) -> tuple[str, str, str, bool]:
    """(kind, version, comment, pinned) of the frozen reference of a
    module."""
    kind, ver = node.kind, node.version
    if node.meta:
        return kind, ver, "meta-module", True
    if node.variant == "native":
        return kind, ver, "OS packages (native variant)", True
    sr = source_ref(driver, node.module)
    if sr is None:
        return kind, ver, "not built: not pinned", False
    origin = f"{sr.origin} {sr.ref}"
    built = f"{origin} {sr.id_kind} {sr.id}".rstrip()
    if kind == "DEV":
        return kind, ver, f"user's checkout, {built}: not pinned", False
    if sr.origin == "none":
        return kind, ver, "no sources", True
    if sr.origin == "archive":
        if sr.ref == ver:
            return "VERSION", sr.ref, built, True
        return kind, ver, f"last built from {origin}: not pinned", False
    expected = display_ref(sr.origin, ver)
    if sr.ref != expected:
        return kind, ver, f"last built from {origin}: not pinned", False
    if sr.origin not in PINNABLE_VCS:
        return kind, ver, f"{built}: not pinned ({sr.origin})", False
    if not sr.id:
        return kind, ver, f"{origin}, no commit recorded: not pinned", False
    return "BRANCH", sr.id, origin, True


def plan_line(node: Node, kind: str, ver: str) -> str:
    ref = format_ref(node.module, node.variant, kind, ver)
    if "=" in node.plan_key:
        return f"@for {node.plan_key.split('=', 1)[0]} use {ref}"
    return ref


def freeze(driver, builder) -> int:
    roots = root_modules(driver)
    nodes, status = walk(driver, builder, roots)
    if status != 0:
        return 1
    plan = driver.plan
    out = ["# Build plan frozen by scbi show --freeze",
           f"# date: {driver.get('TODAY') or time.strftime('%Y-%m-%d')}",
           f"# plan: {driver.get('SCBI_PLAN') or 'none'}",
           f"# target: {driver.get('SCBI_TARGET')}",
           f"# os: {' '.join(w for w in (driver.get('SCBI_OS_NAME'), driver.get('SCBI_OS_VERSION')) if w)}",
           f"# modules: {' '.join(roots)}"]

    aliases = [f"@alias {a} use {b}" for a, b in sorted(plan.module_alias.items())]
    if aliases:
        out += ["", *aliases]

    out.append("")
    seen: set[str] = set()
    unpinned = 0
    externals: list[str] = []
    for node in nodes:
        if node.external:
            externals.append(node.module)
            continue
        if node.plan_key in seen:
            continue
        seen.add(node.plan_key)
        kind, ver, comment, pinned = pin(driver, node)
        if not pinned:
            unpinned += 1
        out.append(f"# {node.module}: {comment}")
        out.append(plan_line(node, kind, ver))

    skipped = [k[:-len(".skip")] for k in assoc_keys(plan.modver)
               if k.endswith(".skip") and plan.modver[k] == "yes"]
    if skipped:
        out.append("")
        for k in sorted(skipped):
            fm, _, m = k.rpartition("=")
            out.append(f"@for {fm} use {m}:skip" if fm else f"{k}:skip")

    if externals:
        from scbi.walker import get_pkg_version

        out += ["", "# OS packages (not pinned):"]
        for pkg in sorted(set(externals)):
            v = get_pkg_version(driver, pkg)
            out.append(f"#   {pkg}{' ' + v if v else ''}")

    sys.stdout.write("\n".join(out) + "\n")
    sys.stdout.flush()
    if unpinned:
        sys.stderr.write(f"scbi show --freeze: {unpinned} module(s) not pinned, see the comments\n")
    return 0
