"""The paths of the origin sandbox in an installation, and their
relocation to another sandbox.

At upload, the files are scanned for the origin roots (the sandbox and
the global prefix, bytes): each file with an occurrence is listed with its
kind:

- text: a file without NUL in its first 8 KiB (.pc, .la, CMake files,
  scripts and their shebang, *-config): any replacement;
- link: a symbolic link with an absolute target in a root;
- binary: the occurrences are in NUL-terminated strings (ELF RPATH and
  RUNPATH, strings compiled in): replaced in place, the string padded
  with NULs, when the new path is not longer;
- other: an occurrence not in a C string: the installation is not
  relocatable.

The Python byte-code files (*.pyc) embed the path of their source with its
length: they are not stored (Python regenerates them).
"""

from __future__ import annotations

import os
import re

TEXT, LINK, BINARY, OTHER = "text", "link", "binary", "other"
#  the files left out of an entry
EXCLUDED = re.compile(r"(^|/)__pycache__(/|$)|\.pyc$")
#  the longest C string looked for after an occurrence
_CSTRING_MAX = 8192


def _pattern(roots: list[str]) -> re.Pattern:
    """The roots (bytes), the longest first, not followed by a character of
    a file name (/a/sbx is not in /a/sbx2)."""
    alts = sorted({r.rstrip("/") for r in roots if r and r.rstrip("/")}, key=len, reverse=True)
    return re.compile(b"(?:" + b"|".join(re.escape(a.encode(errors="surrogateescape")) for a in alts)
                      + b")(?![A-Za-z0-9_.+~-])")


def _is_text(data: bytes) -> bool:
    return b"\0" not in data[:8192]


def _files(tree: str):
    for dirpath, dirnames, filenames in os.walk(tree):
        for name in sorted(filenames) + sorted(n for n in dirnames if os.path.islink(os.path.join(dirpath, n))):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, tree)
            if EXCLUDED.search(rel):
                continue
            yield rel, path


def scan(tree: str, roots: list[str]) -> list[dict]:
    """The files of ``tree`` with an occurrence of a root: [{path, kind}]."""
    pattern = _pattern(roots)
    out = []
    for rel, path in _files(tree):
        if os.path.islink(path):
            target = os.readlink(path).encode(errors="surrogateescape")
            if os.path.isabs(target) and pattern.match(target):
                out.append({"path": rel, "kind": LINK})
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if not pattern.search(data):
            continue
        if _is_text(data):
            out.append({"path": rel, "kind": TEXT})
            continue
        kind = BINARY
        for m in pattern.finditer(data):
            end = data.find(b"\0", m.end(), m.end() + _CSTRING_MAX)
            if end < 0:
                kind = OTHER
                break
        out.append({"path": rel, "kind": kind})
    return out


def relocatable(files: list[dict]) -> bool:
    return all(f["kind"] != OTHER for f in files)


class RelocationError(Exception):
    """The installation cannot be relocated here."""


def relocate(tree: str, files: list[dict], mapping: list[tuple[str, str]]) -> None:
    """Replaces in the listed files the origin roots by the local ones
    (mapping: (origin, local) pairs)."""
    mapping = [(o.rstrip("/"), n.rstrip("/")) for o, n in mapping if o.rstrip("/") != n.rstrip("/")]
    if not mapping:
        return
    table = {o.encode(errors="surrogateescape"): n.encode(errors="surrogateescape") for o, n in mapping}
    pattern = _pattern([o for o, _ in mapping])

    def sub(data: bytes) -> bytes:
        return pattern.sub(lambda m: table[m.group(0)], data)

    for entry in files:
        path = os.path.join(tree, entry["path"])
        kind = entry["kind"]
        if kind == LINK:
            target = os.readlink(path).encode(errors="surrogateescape")
            os.unlink(path)
            os.symlink(sub(target).decode(errors="surrogateescape"), path)
            continue
        with open(path, "rb") as f:
            data = f.read()
        if kind == TEXT:
            new = sub(data)
        elif kind == BINARY:
            new = _sub_cstrings(data, pattern, sub)
        else:
            raise RelocationError(f"{entry['path']}: not relocatable")
        if new != data:
            mode = os.stat(path).st_mode
            #  written in place (hard links, mode kept)
            os.chmod(path, mode | 0o200)
            with open(path, "r+b") as f:
                f.write(new)
                f.truncate()
            os.chmod(path, mode)


def _sub_cstrings(data: bytes, pattern: re.Pattern, sub) -> bytes:
    """The occurrences replaced in their C string, padded with NULs to its
    length; RelocationError when a new string is longer."""
    out = bytearray()
    pos = 0
    for m in pattern.finditer(data):
        if m.start() < pos:
            continue
        end = data.find(b"\0", m.end(), m.end() + _CSTRING_MAX)
        if end < 0:
            raise RelocationError("an occurrence not in a C string")
        segment = data[m.start():end]
        new = sub(segment)
        if len(new) > len(segment):
            raise RelocationError("the local path is longer than the origin one (in a binary file)")
        out += data[pos:m.start()] + new + b"\0" * (len(segment) - len(new))
        pos = end
    out += data[pos:]
    return bytes(out)


def remaining(tree: str, files: list[dict], mapping: list[tuple[str, str]]) -> list[str]:
    """The listed files still holding an origin root after relocation
    (not checked for a root which starts the local one)."""
    roots = [o for o, n in mapping
             if o.rstrip("/") != n.rstrip("/") and not (n.rstrip("/") + "/").startswith(o.rstrip("/") + "/")]
    if not roots:
        return []
    pattern = _pattern(roots)
    left = []
    for entry in files:
        path = os.path.join(tree, entry["path"])
        if entry["kind"] == LINK:
            data = os.readlink(path).encode(errors="surrogateescape")
        else:
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
        if pattern.search(data):
            left.append(entry["path"])
    return left
