"""An entry of a binary store: ``<key>.tar.<zst|xz>`` and ``<key>.json``.

The tarball holds ``install/`` (the installation of the module in its
sandbox, as copied to the global prefix) and ``meta/`` (source-ref,
build-id, build-deps and the logs of the steps). The JSON holds the
metadata: the key and its kind, the components, the module, the origin
paths, the relocation list, the SHA-256 and the size of the tarball.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time

from scbi.binstore import relocate

FORMAT = 1
#  compression: (suffix, tool, compress args, decompress args)
COMPRESSIONS = (
    ("zst", "zstd", ["-q", "-T0", "-3"], ["-q", "-d", "-c"]),
    ("xz", "xz", ["-q", "-T0", "-3", "-c"], ["-q", "-d", "-c"]),
)


class BlobError(Exception):
    pass


def compression(which, name: str = ""):
    """The compression to use (the first available), or the one named."""
    for c in COMPRESSIONS:
        if (not name or c[0] == name) and which(c[1]):
            return c
    return None


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pack(driver, tvdir: str, meta_files: dict[str, str], logs_dir: str, roots: list[str],
         workdir: str) -> tuple[str, dict]:
    """The tarball of the installation (in ``workdir``) and the metadata
    to complete: (path, {compression, relocations, relocatable})."""
    comp = compression(driver.which)
    if comp is None:
        raise BlobError("neither zstd nor xz found")
    suffix, tool, cargs, _ = comp
    install = os.path.join(tvdir, "install")
    files = relocate.scan(install, roots)
    stage = tempfile.mkdtemp(prefix="meta-", dir=workdir)
    meta = os.path.join(stage, "meta")
    os.makedirs(os.path.join(meta, "logs"))
    for name, src in meta_files.items():
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(meta, name))
    if os.path.isdir(logs_dir):
        for name in sorted(os.listdir(logs_dir)):
            src = os.path.join(logs_dir, name)
            if name.endswith(".log") and os.path.isfile(src):
                shutil.copyfile(src, os.path.join(meta, "logs", name))
    out = os.path.join(workdir, f"blob.tar.{suffix}")
    tar = subprocess.Popen(["tar", "-cf", "-", "--exclude=__pycache__", "--exclude=*.pyc",
                            "-C", tvdir, "install", "-C", stage, "meta"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with open(out, "wb") as f:
        rc = subprocess.run([tool, *cargs], stdin=tar.stdout, stdout=f, stderr=subprocess.PIPE).returncode
    assert tar.stdout is not None
    tar.stdout.close()
    trc = tar.wait()
    shutil.rmtree(stage, ignore_errors=True)
    if rc != 0 or trc != 0:
        raise BlobError("cannot create the tarball")
    return out, {"compression": suffix, "relocations": files, "relocatable": relocate.relocatable(files)}


def metadata(driver, key: str, kind: str, comps: dict, module: str, variant: str, ref: str,
             tarball: str, extra: dict, origin_roots: dict[str, str]) -> dict:
    return {
        "format": FORMAT,
        "key": key,
        "kind": kind,
        "module": module,
        "variant": variant,
        "ref": ref,
        "target": driver.get("SCBI_TARGET"),
        "scbi": driver.get("SCBI_VERSION"),
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "origin": origin_roots,
        "components": comps,
        "tarball": {"sha256": sha256(tarball), "size": os.path.getsize(tarball),
                    "compression": extra["compression"]},
        "relocations": extra["relocations"],
    }


def unpack(driver, meta: dict, tarball: str, tvdir: str, local_roots: dict[str, str]) -> None:
    """Extracts the installation into ``<tvdir>/install`` (the logs of the
    origin build in ``<tvdir>/logs/origin``) and relocates it; BlobError
    or RelocationError (nothing left installed) on a failure."""
    if sha256(tarball) != meta["tarball"]["sha256"]:
        raise BlobError("corrupted (SHA-256)")
    comp = compression(driver.which, meta["tarball"]["compression"])
    if comp is None:
        raise BlobError(f"no tool to uncompress {meta['tarball']['compression']}")
    _, tool, _, dargs = comp
    stage = tempfile.mkdtemp(prefix="unpack-", dir=tvdir)
    try:
        with open(tarball, "rb") as f:
            dec = subprocess.Popen([tool, *dargs], stdin=f, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert dec.stdout is not None
            rc = subprocess.run(["tar", "-xf", "-", "-C", stage], stdin=dec.stdout,
                                stderr=subprocess.PIPE).returncode
            dec.stdout.close()
            if dec.wait() != 0 or rc != 0:
                raise BlobError("cannot extract the tarball")
        install = os.path.join(stage, "install")
        if not os.path.isdir(install):
            os.makedirs(install)
        mapping = [(path, local_roots[k]) for k, path in meta["origin"].items()
                   if path and local_roots.get(k)]
        relocate.relocate(install, meta.get("relocations", []), mapping, patchelf=driver.which("patchelf"))
        left = relocate.remaining(install, meta.get("relocations", []), mapping)
        if left:
            raise relocate.RelocationError(f"origin paths left in {', '.join(left[:3])}")
        dest = os.path.join(tvdir, "install")
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(install, dest)
        logs = os.path.join(stage, "meta", "logs")
        if os.path.isdir(logs):
            origin = os.path.join(tvdir, "logs", "origin")
            shutil.rmtree(origin, ignore_errors=True)
            os.makedirs(os.path.dirname(origin), exist_ok=True)
            os.replace(logs, origin)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def roots(driver) -> dict[str, str]:
    """The paths of the sandbox and of the prefix (as set, and real) found
    in the installed files: the origin ones in an entry, the local ones to
    relocate to."""
    out: dict[str, str] = {}
    for name, var in (("bdir", "SCBI_BDIR"), ("prefix", "SCBI_PREFIX")):
        value = driver.get(var).rstrip("/")
        if value:
            out[name] = value
            out[f"{name}-real"] = os.path.realpath(value)
    return out


def dumps(meta: dict) -> bytes:
    return (json.dumps(meta, indent=1, sort_keys=True) + "\n").encode()
