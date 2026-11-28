"""scbi binary-store: the binary stores (scbi.binstore).

    scbi binary-store --show-key [modules]   the binary keys of the modules
                                             of the build and the stores
                                             having them
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile

USAGE = """
SCBI-BINARY-STORE {version}

{argv0} binary-store [options] [plug-in...]

   -h | --help             this help message
      | --show-key         binary keys of the modules and the stores having them"""


def main(driver, args: list[str]) -> int:
    proc = subprocess.run(["getopt", "-o", "", "-l", "show-key", "--", *args],
                          capture_output=True, text=True, env=driver.base_env())
    if proc.returncode != 0:
        sys.stdout.write(proc.stderr)
        print('try "scbi binary-store --help" for more information.')
        return 1
    show_key = False
    for a in shlex.split(proc.stdout):
        if a == "--show-key":
            show_key = True
    if driver.get("DO_HELP") == "yes" or not show_key:
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0
    return show_keys(driver)


def _has(store, path: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            return store.get(path, os.path.join(tmp, "entry.json"))
        except Exception:  # noqa: BLE001 - not reachable: not found
            return False


def show_keys(driver) -> int:
    """The keys recorded by the last build of each module (relocatable,
    bound) and the stores having them."""
    from scbi.binstore import flow, key, stores
    from scbi.build import Builder
    from scbi.tools.planwalk import root_modules, walk

    driver.set("DO_QUIET", "yes")
    builder = Builder(driver)
    nodes, status = walk(driver, builder, root_modules(driver))
    if status != 0:
        return 1
    target = driver.get("SCBI_TARGET")
    all_stores = stores.stores(driver)
    seen = set()
    for node in nodes:
        if node.external or node.module in seen:
            continue
        seen.add(node.module)
        name = node.module if node.variant == "default" else f"{node.module}/{node.variant}"
        tvdir = builder.target_dir(node.module, node.variant)
        try:
            with open(os.path.join(tvdir, flow.KEY_FILE)) as f:
                kr = f.read().strip()
        except OSError:
            print(f"{name}: no binary key")
            continue
        comps = None
        try:
            with open(os.path.join(tvdir, f"{flow.KEY_FILE}.json")) as f:
                comps = json.load(f)
        except (OSError, ValueError):
            pass
        keys = [("relocatable", kr)]
        if comps is not None:
            keys.append(("bound", key.keys(driver, comps)[1]))
        print(f"{name}:")
        for kind, k in keys:
            where = [s.url for s in all_stores
                     if _has(s, flow.entry_path(target, node.module, f"{k}.json"))]
            print(f"  {kind:<11} {k}  {', '.join(where) if where else 'not in a store'}")
    return 0
