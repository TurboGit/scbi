"""Extraction of an archive (the second part of get-archive): unpack it
in a temporary directory, then move the sources to archive-src (the
single top directory, or the given sub-directory, or everything)."""

from __future__ import annotations

import os
import shutil

from scbi.bashcompat import words

#  (substring of the archive name, tool checked, command)
UNPACKERS = [
    (".zip", "unzip", lambda path: ["unzip", path]),
    (".7z", "7z", lambda path: ["7z", "x", path]),
]
MISSING = {"unzip": "missing unzip tool to decompress this archive",
           "7z": "missing 7z tool to decompress this archive",
           "unzstd": "missing zst tool to decompress this archive"}


def _tool(name: str, env: dict[str, str]) -> bool:
    return shutil.which(name, path=env.get("PATH")) is not None


def unpack(io, tmp: str, path: str, tarsrc: str, env: dict[str, str], elog) -> int | None:
    """Unpack the archive in ``tmp`` (output to the log); None when a tool
    is missing (error reported)."""
    if "tar.zst" in tarsrc and not _tool("unzstd", env):
        elog(*MISSING["unzstd"].split())
        return None
    for marker, tool, command in UNPACKERS:
        if marker in tarsrc:
            if not _tool(tool, env):
                elog(*MISSING[tool].split())
                return None
            return io.run(command(path), tmp)
    return io.run(["tar", "xf", path], tmp)


def move_sources(io, tmp: str, dest: str, tardir: str, tarsrc: str, elog) -> bool:
    entries = words("\n".join(sorted(e for e in os.listdir(tmp) if not e.startswith("."))))
    if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])):
        top = entries[0]
        if tardir:
            if os.path.isdir(os.path.join(tmp, top, tardir)):
                io.run(["mv", f"{top}/{tardir}", "../archive-src"], tmp)
            else:
                elog("no", "directory", *words(tardir), "in", "archive", *words(tarsrc))
                return False
        else:
            io.run(["mv", top, "../archive-src"], tmp)
    elif tardir:
        if os.path.isdir(os.path.join(tmp, tardir)):
            io.run(["mv", tardir, "../archive-src"], tmp)
        else:
            elog("no", "directory", *words(tardir), "in", "archive", *words(tarsrc))
            return False
    else:
        #  no top directory: everything, hidden files included
        os.makedirs(dest, exist_ok=True)
        io.run(["bash", "-c", "mv * .* ../archive-src"], tmp)
    return True
