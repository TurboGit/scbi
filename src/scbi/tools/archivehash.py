"""scbi show --archive-sha256: the lines of the archive-sha256 hook
(``<sha256>  <file>``, as sha256sum prints them) of the archives of the
modules of the build, computed from the archive store, to paste in the
plug-ins."""

from __future__ import annotations

import os
import sys

from scbi.sources.archive.fetch import file_sha256
from scbi.sources.data import archive_data
from scbi.tools.planwalk import root_modules, source_ref, walk


def archive_file(driver, builder, node) -> tuple[str, str] | None:
    """(version, file) of the archive of a module: the one of its last
    build, else the one of its module reference; None without archive."""
    sr = source_ref(driver, node.module)
    if sr is not None and sr.origin == "archive":
        version = sr.ref
    elif node.kind == "VERSION":
        version = node.version
    else:
        return None
    data, rc = archive_data(builder, node.module, node.variant, version)
    if rc != 0 or len(data) < 6 or data[5].upper() == "NONE":
        return None
    return version, data[5]


def show(driver, builder) -> int:
    nodes, status = walk(driver, builder, root_modules(driver))
    if status != 0:
        return 1
    archives = driver.get("SCBI_ARCHIVES")
    out: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        if node.external or node.meta or node.variant == "native":
            continue
        found = archive_file(driver, builder, node)
        if found is None or (node.module, found[1]) in seen:
            continue
        seen.add((node.module, found[1]))
        path = os.path.join(archives, found[1])
        if os.path.isfile(path):
            out += [f"# {node.module}", f"{file_sha256(path)}  {found[1]}"]
        else:
            out.append(f"# {node.module}: {found[1]} not downloaded")
    if out:
        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()
    return 0
