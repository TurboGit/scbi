"""The removal of the entries of the binary stores: scbi binary-store
--rm and --gc, and the size limit SCBI_BINARY_STORE_MAX_SIZE applied to
the writable stores at the end of a build.

An entry is the files ``<key>.json``, ``<key>.tar.*`` and
``<key>.json.sig`` of ``<target>/<module>/``. Its last use is the time of
its JSON in a file store (updated when it is installed), else its date.
The least recently used entries are removed first; the JSON first, so
that a removed entry is never found half there.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field

from scbi.binstore import stores

_UNITS = {"": 1, "K": 1 << 10, "M": 1 << 20, "G": 1 << 30, "T": 1 << 40}
_AGES = {"": 86400, "d": 86400, "h": 3600, "w": 7 * 86400}


def parse_size(text: str) -> int:
    """A size: a number, possibly followed by K, M, G or T."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]?)i?B?\s*", text, re.I)
    if not m:
        raise ValueError(f"{text!r}: not a size (e.g. 500M, 20G)")
    return int(float(m.group(1)) * _UNITS[m.group(2).upper()])


def parse_age(text: str) -> float:
    """An age in seconds: a number of days, or with h, d or w."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([dhw]?)\s*", text)
    if not m:
        raise ValueError(f"{text!r}: not an age (e.g. 30 or 30d, 12h, 4w)")
    return float(m.group(1)) * _AGES[m.group(2)]


@dataclass
class Entry:
    target: str
    module: str
    key: str
    files: list[str] = field(default_factory=list)
    size: int = 0
    last_used: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def json(self) -> str:
        return f"{self.target}/{self.module}/{self.key}.json"


def _date(meta: dict) -> float:
    try:
        return float(calendar.timegm(time.strptime(meta.get("date", ""), "%Y-%m-%dT%H:%M:%SZ")))
    except (ValueError, TypeError):
        return 0.0


def entries(store: stores.Store) -> list[Entry]:
    """The entries of a store (all the targets and modules)."""
    out: list[Entry] = []
    with tempfile.TemporaryDirectory() as tmp:
        for target in store.list(""):
            for module in store.list(target):
                names = store.list(f"{target}/{module}")
                for name in names:
                    if not name.endswith(".json"):
                        continue
                    key = name[:-len(".json")]
                    e = Entry(target, module, key,
                              files=[n for n in names if n.startswith(key + ".") and n != name] + [name])
                    path = os.path.join(tmp, "entry.json")
                    try:
                        if store.get(e.json, path):
                            with open(path) as f:
                                e.meta = json.load(f)
                    except (OSError, ValueError, stores.StoreError):
                        pass
                    e.size = int(e.meta.get("tarball", {}).get("size", 0))
                    e.last_used = store.last_used(e.json) or _date(e.meta)
                    out.append(e)
    return out


def remove(store: stores.Store, entry: Entry) -> None:
    """The JSON first, then the other files of the entry."""
    store.delete(entry.json)
    for name in entry.files:
        if name != f"{entry.key}.json":
            store.delete(f"{entry.target}/{entry.module}/{name}")


def collect(store: stores.Store, max_size: int | None = None, older_than: float | None = None,
            now: float | None = None) -> tuple[list[Entry], list[Entry]]:
    """The entries to remove (least recently used first) so that none is
    older than ``older_than`` seconds and the store is not larger than
    ``max_size`` bytes: (removed, kept)."""
    now = time.time() if now is None else now
    all_entries = sorted(entries(store), key=lambda e: e.last_used)
    removed, kept = [], []
    for e in all_entries:
        if older_than is not None and now - e.last_used > older_than:
            removed.append(e)
        else:
            kept.append(e)
    if max_size is not None:
        total = sum(e.size for e in kept)
        while kept and total > max_size:
            e = kept.pop(0)
            total -= e.size
            removed.append(e)
    return removed, kept


def auto(driver) -> None:
    """SCBI_BINARY_STORE_MAX_SIZE: the writable stores reduced to this size
    at the end of a build (a warning on a failure)."""
    value = driver.get("SCBI_BINARY_STORE_MAX_SIZE")
    if not value:
        return
    try:
        max_size = parse_size(value)
    except ValueError as e:
        driver.log.ilog("build", f"warning: SCBI_BINARY_STORE_MAX_SIZE: {e}")
        return
    for store in stores.stores(driver):
        if not store.writable:
            continue
        try:
            removed, _ = collect(store, max_size=max_size)
            for e in removed:
                remove(store, e)
        except stores.StoreError as e:
            driver.log.ilog("build", f"warning: binary store: {e}")
