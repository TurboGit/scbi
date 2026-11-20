"""Build identifiers (ports of get-build-id, get-depends-build-id,
get-patch-md5 and the md5 helpers of scripts.d/5_tools).

A build id is the md5 of everything a build depends on: the sources id
(vid), the module reference, target and OS, the plug-in resolved for the
module reference without its env hook (scbi.plugin.resolved: comments,
formatting, other variants and unused hooks do not count), the build
types, the patches, the build ids and the env hooks of the direct
dependencies and the external-env values.
"""

from __future__ import annotations

import hashlib
import os
import time

from scbi.bashcompat import words
from scbi.errors import Exit


def md5(data: bytes) -> str:
    """``get-md5``: md5sum of the data, the hash only."""
    return hashlib.md5(data).hexdigest()


def string_md5(value: str) -> str:
    """``output-string-md5 VALUE``: md5 of ``echo $1`` (unquoted: words
    joined by a space)."""
    return md5((" ".join(words(value)) + "\n").encode(errors="surrogateescape"))


def file_md5(path: str) -> str:
    """``cat FILE | get-md5`` (a missing file gives the md5 of nothing)."""
    try:
        with open(path, "rb") as f:
            return md5(f.read())
    except OSError:
        return md5(b"")


def patch_md5(builder, patch: str) -> str:
    """``get-patch-md5 FILE``."""
    d = builder.d
    for path in (f"{d.get('SCBI_PATCH')}/{patch}", f"{d.get('SCBI_PLUGINS')}/patches/{patch}"):
        if os.path.isfile(path):
            return file_md5(path)
    return "not-found"


def depends_build_id(builder, modref: str) -> str:
    """``get-depends-build-id MODREF``: md5 of the build ids of the direct
    dependencies (of the modules of a meta-module) and of their env hooks
    (resolved: the environment they give to this build; the env hooks of
    the deeper dependencies are in the build ids of the direct ones),
    whatever the order of the dependencies (the chunks are sorted); run
    in a sub-shell in Bash, so an exit of the walker only ends the list."""
    from scbi.plugin.resolved import env_md5
    from scbi.walker import Walker

    d = builder.d
    walker = Walker(builder)
    module, variant = (d.plan.module_ref(modref) + ["", ""])[:2]
    walker.load_module(modref)
    is_meta = d.registry.loaded.get(f"{module}.{variant}") == "meta"
    max_level = 0 if is_meta else 1
    out: list[bytes] = []
    pkgs = d.sv.arrays.get("SCBI_PKGS", ("A", {}))[1]

    def callback(argv: list[str]) -> None:
        a = (argv + [""] * 7)[:7]
        formodule, ref, level, _kind, is_ext, meta = a[:6]
        if _int(level) >= max_level and meta == "false":
            m, v = (d.plan.module_ref(ref, formodule) + ["", ""])[:2]
            #  one chunk per dependency
            if is_ext == "true":
                out.append((" ".join(words(pkgs.get(m, ""))) + "\n").encode())
            else:
                path = f"{d.get('SCBI_BDIR')}/{m}/build-id-{v}"
                if os.path.isfile(path):
                    with open(path, "rb") as f:
                        chunk = f.read()
                else:
                    chunk = time.strftime("%c").encode()
                out.append(chunk + f"env {m} {env_md5(d, m, v)}\n".encode())

    name = "get-meta-build-id-callback" if is_meta else "get-build-id-callback"
    try:
        walker.walk("for-all-direct-modules-with-meta-ext", callback, modref, name=name)
    except Exit:
        pass
    #  the order of the dependencies does not count
    return md5(b"".join(sorted(out)))


def build_id(builder, prefix: str, target: str, formodule: str, modref: str, vid: str) -> str:
    """``get-build-id PREFIX TARGET FORMODULE MODREF VID`` (output, no
    newline)."""
    from scbi.plugin.resolved import resolved_md5

    d = builder.d
    module, variant, kind, ref = (d.plan.module_ref(modref, formodule) + [""] * 4)[:4]
    mid = f"{variant}:{ref},{target},{d.get('SCBI_OS_VERSION')},{d.get('SCBI_OS_CODENAME')}"
    #  the plug-in resolved for the module reference (its inherited
    #  plug-ins included), without its env hook
    hid = ""
    if d.registry.plugin_file(module) is not None:
        hid = resolved_md5(d, module, variant, kind, ref)

    value = d.get(f"SCBI_{module.replace('-', '_')}_BUILD_TYPE")
    if value:
        mid += f",{value}"
    for b in ("CMAKE", "CONFIGURE", "MAKE", "GPR"):
        value = d.get(f"SCBI_{b}_BUILD_TYPE")
        if value:
            mid += f",{value}"

    pid = "no-patch-found"
    if d.get("DO_PATCH") == "yes":
        patches = d.runner().variant_values(module, variant, "patches", [prefix, target, variant, kind, ref],
                                           d.plan, builder.modules_list)
        for patch in words("\n".join(patches)):
            pid += f",{patch_md5(builder, patch)}"

    did = depends_build_id(builder, modref)

    eid = ""
    extenv = d.runner().variant_values(module, variant, "external-env", [prefix, target, variant],
                                       d.plan, builder.modules_list)
    for e in words("\n".join(extenv)):
        eid += f",{e}"

    return string_md5(f"{vid},{mid},{hid},{pid},{did}{eid}")


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0
