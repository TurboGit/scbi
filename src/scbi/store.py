from __future__ import annotations

import os
from pathlib import Path


class Store:
    def __init__(self, store_path: Path | None = None):
        self.store_path = store_path or Path.cwd() / ".store"

    def get_key(self, key: str) -> tuple[str | None, bool]:
        if not self.store_path.is_file():
            return (None, False)
        with open(str(self.store_path)) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) >= 1 and parts[0] == key:
                    val = parts[1] if len(parts) > 1 else ""
                    return (val, True)
        return (None, False)

    def set_key(self, key: str, value: str) -> None:
        store: dict[str, str] = {}
        if self.store_path.is_file():
            with open(str(self.store_path)) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(None, 1)
                    if len(parts) >= 1:
                        k = parts[0]
                        v = parts[1] if len(parts) > 1 else ""
                        store[k] = v

        store[key] = value

        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.store_path), "w") as f:
            for k, v in store.items():
                f.write(f"{k} {v}\n")

    def list_keys(self) -> list[str]:
        if not self.store_path.is_file():
            return []
        keys: list[str] = []
        with open(str(self.store_path)) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if parts:
                    keys.append(parts[0])
        return keys
