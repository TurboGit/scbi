"""Inputs collected from the repository, used by the oracle tests."""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

from oracle import REPO_ROOT

PLUGIN_DIRS = [REPO_ROOT / "scripts.d", REPO_ROOT / "tests" / "scripts.d"]


@cache
def plan_files() -> list[Path]:
    files: list[Path] = []
    for d in PLUGIN_DIRS:
        files += sorted(p for p in d.glob(".plan-*") if not p.name.endswith("~"))
    return files


@cache
def plugin_files() -> list[Path]:
    """Plug-in files: not runtime files ([0-9]*, _os_*), dot or backup files."""
    files: list[Path] = []
    for d in PLUGIN_DIRS:
        for p in sorted(d.iterdir()):
            if p.is_file() and not re.match(r"[0-9._]", p.name) and not p.name.endswith("~"):
                files.append(p)
    return files


@cache
def plan_tokens() -> list[str]:
    """Every word found in plan files (module refs, keywords, barriers...)."""
    tokens: set[str] = set()
    for f in plan_files():
        for line in f.read_text().splitlines():
            line = line.split("#", 1)[0]
            tokens.update(line.split())
    return sorted(tokens)


DOC_MODREFS = [
    "lcms2",
    "lcms2/fast",
    "gimp=lcms2/slow",
    "lcms2:v2.0",
    "lcms2/fast:v2.0",
    "lcms2/@:v2.0",
    "lcms2:bfaf7b82ed",
    "lcms2:#v1.0",
    "lcms2:dev",
    "lcms2:skip",
    "lcms2:keep",
    "lcms2:force",
    "lcms2:@",
    "module/auto.fast:v1.3",
    "mod/mpi.openmp",
    "c-gmp/native",
    "os@-gmp-dev:[v]",
]

EDGE_MODREFS = [
    "a:",
    "a/",
    "a/b/c",
    "a/b/c:v1:v2",
    "a:b/c",
    "a=b=c/d:e",
    "/v",
    ":v",
    "a:#",
    "a:##1",
    "a/:dev",
    "a/x..y",
    "a/.x",
]


def modrefs() -> list[str]:
    refs = set(DOC_MODREFS) | set(EDGE_MODREFS)
    refs |= {t for t in plan_tokens() if not t.startswith(("@", "[", "]", "="))}
    return sorted(refs)


VERSIONS = [
    "1", "1.0", "1.0.0", "1.0.1", "1.1", "1.10", "1.9", "2", "2.0", "2.0.1",
    "v1.0", "V1.0", "v2.0.3", "10.2", "3.0003", "3.0000004", "1.0rc1", "1.0rc2",
    "1.0-2", "1.0.a", "1.0b", "2.0beta", "7.8", "7.8.1", "12", "0.9.99",
    "1..2", ".1", "1.", "master", "gdb-head",
]

OPS = ["=", "==", "!=", "<", "<=", ">", ">="]


def version_strings() -> list[str]:
    found: set[str] = set(VERSIONS)
    for t in plan_tokens():
        if ":" in t:
            v = t.split(":", 1)[1]
            if re.fullmatch(r"[#vV]?[0-9][0-9A-Za-z.\-]*", v):
                found.add(v.lstrip("#"))
    return sorted(found)
