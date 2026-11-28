"""scbi binary-store: the binary stores (scbi.binstore).

    scbi binary-store --show-key [modules]   the binary keys of the modules
                                             of the build and the stores
                                             having them
    scbi binary-store --list [modules]       the entries of the stores
    scbi binary-store --explain <module>     why the entries of the stores
                                             do not match the last build
    scbi binary-store --gc [--max-size=S] [--older-than=D] [--dry-run]
                                             remove the least recently used
                                             entries of the writable stores
    scbi binary-store --rm <key>...          remove entries (a key prefix of
                                             at least 8 characters)
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
      | --show-key         binary keys of the modules and the stores having them
      | --list             entries of the stores (of the modules given)
      | --explain          what differs between the last build and the entries
      | --gc               remove the least recently used entries (writable stores)
      | --max-size=<S>     with --gc: the size of a store (500M, 20G...)
      | --older-than=<D>   with --gc: entries not used for D days (or 12h, 4w)
      | --rm               remove the entries of the keys given
      | --dry-run          with --gc and --rm: display, do not remove"""


def main(driver, args: list[str]) -> int:
    proc = subprocess.run(["getopt", "-o", "", "-l", "show-key,list,explain,gc,rm,max-size:,older-than:,dry-run",
                           "--", *args],
                          capture_output=True, text=True, env=driver.base_env())
    if proc.returncode != 0:
        sys.stdout.write(proc.stderr)
        print('try "scbi binary-store --help" for more information.')
        return 1
    action = ""
    opts: dict[str, str] = {}
    parsed = shlex.split(proc.stdout)
    i = 0
    while i < len(parsed):
        a = parsed[i]
        if a in ("--show-key", "--list", "--explain", "--gc", "--rm"):
            action = a[2:]
        elif a in ("--max-size", "--older-than"):
            opts[a[2:]] = parsed[i + 1] if i + 1 < len(parsed) else ""
            i += 1
        elif a == "--dry-run":
            opts["dry-run"] = "yes"
        elif a == "--":
            #  the modules (the keys of --rm), after the options
            driver.modules = parsed[i + 1:]
            break
        i += 1
    if driver.get("DO_HELP") == "yes" or not action:
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0
    if action == "list":
        return list_entries(driver)
    if action == "gc":
        return garbage_collect(driver, opts)
    if action == "rm":
        return remove_keys(driver, opts)
    if action == "explain":
        return explain(driver)
    return show_keys(driver)


def _entries(driver, store, module: str) -> list[dict]:
    """The metadata of the entries of a module in a store."""
    from scbi.binstore import flow

    target = driver.get("SCBI_TARGET")
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in store.list(f"{target}/{module}"):
            if not name.endswith(".json"):
                continue
            path = os.path.join(tmp, name)
            try:
                if store.get(flow.entry_path(target, module, name), path):
                    with open(path) as f:
                        out.append(json.load(f))
            except Exception:  # noqa: BLE001 - an entry not readable: skipped
                continue
    return out


def list_entries(driver) -> int:
    """The entries of the stores, for the modules given or all."""
    from scbi.bashcompat import words
    from scbi.binstore import stores

    target = driver.get("SCBI_TARGET")
    modules = words(" ".join(driver.modules))
    for store in stores.stores(driver):
        print(f"{store.url} ({store.mode}):")
        names = [m.split("/", 1)[0].split(":", 1)[0] for m in modules] or store.list(target)
        for module in names:
            for meta in sorted(_entries(driver, store, module), key=lambda m: (m.get("variant", ""), m.get("date", ""))):
                size = meta.get("tarball", {}).get("size", 0)
                variant = meta.get("variant", "default")
                name = module if variant == "default" else f"{module}/{variant}"
                ref = meta.get("ref") or "NONE"
                print(f"  {name:<30} {ref:<12} {meta.get('kind', ''):<11} {size / 1048576:8.1f} MB  "
                      f"{meta.get('date', '')}  {meta.get('origin', {}).get('bdir', '')}  {meta.get('key', '')[:16]}")
    return 0


def _differences(local: dict, other: dict) -> list[str]:
    """What differs between two key components, for a reader."""
    out = []
    for name in sorted(set(local) | set(other)):
        a, b = local.get(name), other.get(name)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                if a.get(k) != b.get(k):
                    out.append(f"{name}: {k}: {a.get(k, '(none)')!r} here, {b.get(k, '(none)')!r} in the entry")
        else:
            out.append(f"{name}: {a!r} here, {b!r} in the entry")
    return out


def explain(driver) -> int:
    """Compares the components of the last build of the module with the
    entries of the stores of the same module and variant."""
    from scbi.bashcompat import words
    from scbi.binstore import flow, stores
    from scbi.build import Builder

    modules = words(" ".join(driver.modules))
    if len(modules) != 1:
        print("scbi binary-store --explain: one module expected")
        return 1
    driver.set("DO_QUIET", "yes")
    builder = Builder(driver)
    module, variant = (driver.plan.module_ref(modules[0]) + ["", ""])[:2]
    variant = variant or "default"
    tvdir = builder.target_dir(module, variant)
    try:
        with open(os.path.join(tvdir, f"{flow.KEY_FILE}.json")) as f:
            local = json.load(f)
    except (OSError, ValueError):
        print(f"{module}: no binary key recorded (not built with a binary store)")
        return 1
    found = False
    for store in stores.stores(driver):
        for meta in _entries(driver, store, module):
            if meta.get("variant", "default") != variant:
                continue
            found = True
            comps = dict(meta.get("components", {}))
            bound = comps.pop("location", None)
            diffs = _differences(local, comps)
            head = f"{store.url}: {meta.get('key', '')[:16]} ({meta.get('kind', '')}, {meta.get('date', '')}, " \
                   f"{meta.get('origin', {}).get('bdir', '')})"
            if not diffs:
                print(f"{head}: same components" + (", bound to its sandbox" if bound else ""))
            else:
                print(f"{head}:")
                for line in diffs:
                    print(f"  {line}")
    if not found:
        print(f"{module}: no entry in the stores")
    return 0


def _describe(e) -> str:
    variant = e.meta.get("variant", "default")
    name = e.module if variant == "default" else f"{e.module}/{variant}"
    return f"{name} {e.key[:16]} ({e.size / 1048576:.1f} MB)"


def garbage_collect(driver, opts: dict[str, str]) -> int:
    """--gc: the writable stores reduced (age, size), the least recently
    used entries first."""
    from scbi.binstore import gc, stores

    try:
        max_size = gc.parse_size(opts["max-size"]) if opts.get("max-size") else None
        older = gc.parse_age(opts["older-than"]) if opts.get("older-than") else None
    except ValueError as e:
        print(f"scbi binary-store: {e}")
        return 1
    if max_size is None and older is None:
        value = driver.get("SCBI_BINARY_STORE_MAX_SIZE")
        if not value:
            print("scbi binary-store --gc: --max-size or --older-than expected (or SCBI_BINARY_STORE_MAX_SIZE)")
            return 1
        max_size = gc.parse_size(value)
    dry = opts.get("dry-run") == "yes"
    status = 0
    for store in stores.stores(driver):
        if not store.writable:
            continue
        removed, kept = gc.collect(store, max_size=max_size, older_than=older)
        print(f"{store.url}: {len(removed)} entr{'y' if len(removed) == 1 else 'ies'} "
              f"{'to remove' if dry else 'removed'} ({sum(e.size for e in removed) / 1048576:.1f} MB), "
              f"{len(kept)} kept ({sum(e.size for e in kept) / 1048576:.1f} MB)")
        for e in removed:
            print(f"  {_describe(e)}")
            if not dry:
                try:
                    gc.remove(store, e)
                except stores.StoreError as err:
                    print(f"  warning: {err}")
                    status = 1
    return status


def remove_keys(driver, opts: dict[str, str]) -> int:
    """--rm: the entries of the keys (prefixes of 8 characters at least) in
    the writable stores."""
    from scbi.bashcompat import words
    from scbi.binstore import gc, stores

    keys = words(" ".join(driver.modules))
    if not keys or any(len(k) < 8 for k in keys):
        print("scbi binary-store --rm: keys (8 characters at least) expected")
        return 1
    dry = opts.get("dry-run") == "yes"
    found = 0
    for store in stores.stores(driver):
        if not store.writable:
            continue
        for e in gc.entries(store):
            if any(e.key.startswith(k) for k in keys):
                found += 1
                print(f"{store.url}: {'to remove' if dry else 'removed'} {_describe(e)}")
                if not dry:
                    gc.remove(store, e)
    if not found:
        print("scbi binary-store --rm: no entry found")
        return 1
    return 0


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
