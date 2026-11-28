"""The binary key of a build: SHA-256 of the canonical JSON of its
components. Two builds have the same key when their installations are
interchangeable (up to the paths of the sandbox, relocated).

The components (kept in the metadata of an entry, to explain a miss):

- format: the format of the key;
- build-id: the build id of the module (scbi.sources.buildid);
- depends: the binary keys of the direct dependencies (Merkle);
- env: the environment of the commands of the build, normalized (the
  paths of the sandbox and of the user replaced by placeholders, the
  variables that do not change a build removed);
- os: the OS and the host;
- layout: flat or not;
- extra: values given by the environment file (SCBI_BINARY_KEY_EXTRA and
  the output of its function binary-key MODULE VARIANT TARGET);
- location (bound key only): the paths of the sandbox and of the prefix.

An unknown difference gives another key: a miss, never a wrong hit.
"""

from __future__ import annotations

import hashlib
import json
import os

from scbi.bashcompat import words

FORMAT = 1

#  variables of the environment of the hooks which do not change a build
VOLATILE = frozenset((
    "PWD", "OLDPWD", "SHLVL", "_", "TERM", "DISPLAY", "USER", "LOGNAME", "SHELL",
    "SCBI_JOBS", "SCBI_HALF_JOBS", "SCBI_RUN_ID", "SCBI_CURRENT_MODULE", "SCBI_MODULES_LIST",
    "SCBI_HANDLED", "SCBI_LINE_SEP", "SCBI_VERSION", "SCBI_BINARY", "SCBI_PLAN", "SCBI_ENV_DIR",
    "SCBI_CBOLD", "SCBI_CTEXT", "SCBI_CCLEAR", "SCBI_CRED", "SCBI_CGREEN", "SCBI_CBLUE",
    "SCBI_DLOG", "SCBI_PROGRESS", "SCBI_TEST_PROGRESS", "SCBI_CACHE_DIR", "SCBI_BINARY_STORE",
    "SCBI_BINARY_KEY_IGNORE", "SCBI_BINARY_KEY_EXTRA", "SCBI_PARALLEL_WORKER", "SCBI_PLAN_STATE",
    "SCBI_BUILD_SLOTS_FIFO", "SCBI_NEEDED_BY", "SCBI_NESTED", "SCBI_IS_FROM_CACHE",
    "SCBI_ENV_MODULE", "SCBI_TESTSUITE",
))

#  the directories replaced by a placeholder in the values (the sandbox,
#  the prefix, the plug-ins... and the home directory)
LOCATIONS = (
    ("SCBI_BDIR", "<bdir>"), ("SCBI_PREFIX", "<prefix>"), ("SCBI_PLUGINS", "<plugins>"),
    ("SCBI_ROOT", "<root>"), ("SCBI_ARCHIVES", "<archives>"), ("SCBI_PATCH", "<patches>"),
    ("SCBI_LOGS", "<logs>"), ("HOME", "<home>"),
)


def location_roots(driver) -> list[tuple[str, str]]:
    """(path, placeholder), the longest paths first (both the path and its
    real path)."""
    roots: dict[str, str] = {}
    for var, label in LOCATIONS:
        value = driver.get(var).rstrip("/")
        if not value or value == "/":
            continue
        for p in (value, os.path.realpath(value)):
            roots.setdefault(p, label)
    return sorted(roots.items(), key=lambda r: -len(r[0]))


def normalize(value: str, roots: list[tuple[str, str]]) -> str:
    """The value with the location paths replaced by their placeholder
    (in one pass, the longest first)."""
    if not roots:
        return value
    out = []
    i = 0
    while i < len(value):
        for path, label in roots:
            if value.startswith(path, i) and (len(value) == i + len(path) or value[i + len(path)] in "/:; ="):
                out.append(label)
                i += len(path)
                break
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def environment(driver, env: dict[str, str]) -> dict[str, str]:
    """The env component: the environment of the hooks, normalized."""
    ignore = set(VOLATILE) | set(words(driver.get("SCBI_BINARY_KEY_IGNORE")))
    roots = location_roots(driver)
    return {k: normalize(v, roots) for k, v in sorted(env.items())
            if k not in ignore and not k.startswith("BASH_FUNC_")}


def components(driver, build_id: str, depends: dict[str, str], env: dict[str, str],
               extra: str = "") -> dict:
    """``extra``: the output of the binary-key function of the environment
    file, added to SCBI_BINARY_KEY_EXTRA."""
    g = driver.get
    return {
        "format": FORMAT,
        "build-id": build_id,
        "depends": dict(sorted(depends.items())),
        "env": environment(driver, env),
        "os": {"id": g("SCBI_OS_ID"), "name": g("SCBI_OS_NAME"), "version": g("SCBI_OS_VERSION"),
               "codename": g("SCBI_OS_CODENAME"), "host": g("SCBI_HOST"), "target": g("SCBI_TARGET")},
        "layout": "flat" if g("DO_FLAT") == "yes" else "tree",
        "extra": " ".join(x for x in (g("SCBI_BINARY_KEY_EXTRA"), extra.strip()) if x),
    }


def location(driver) -> dict[str, str]:
    """The location component of a bound key."""
    return {"bdir": os.path.realpath(driver.get("SCBI_BDIR")),
            "prefix": os.path.realpath(driver.get("SCBI_PREFIX") or "/")}


def digest(data: dict) -> str:
    text = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode(errors="surrogateescape")).hexdigest()


def keys(driver, comps: dict) -> tuple[str, str]:
    """(relocatable key, bound key)."""
    return digest(comps), digest(dict(comps, location=location(driver)))
