"""The binary stores: an ordered list of stores, each a URL with a mode
(rw, the default, or ro).

SCBI_BINARY_STORE: the URLs separated by blanks, ``ro:<url>`` read-only;
``no``: no store. Not set: ``file://$HOME/.cache/scbi/binaries``.

A store gives the files of its entries by path (``<target>/<module>/
<key>.json``...): ``get`` (copy to a local file), ``put`` (atomic: a
temporary file renamed) and ``list``. The file store is a directory (a
local disk or a NFS mount).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile

from scbi.bashcompat import words


class StoreError(Exception):
    pass


class Store:
    scheme = ""

    def __init__(self, url: str, mode: str = "rw"):
        self.url = url
        self.mode = mode

    @property
    def writable(self) -> bool:
        return self.mode == "rw"

    def get(self, rel: str, dest: str) -> bool:
        """Copies the file ``rel`` of the store to ``dest``; False when the
        store does not have it."""
        raise NotImplementedError

    def put(self, src: str, rel: str) -> None:
        raise NotImplementedError

    def list(self, rel: str) -> list[str]:
        """The names of the files in the directory ``rel``."""
        return []


class FileStore(Store):
    """A directory: a local disk or a NFS mount. The directories and the
    files are created group-writable (a store shared by a team)."""

    scheme = "file"

    def __init__(self, url: str, mode: str = "rw"):
        super().__init__(url, mode)
        self.root = url[len("file://"):] if url.startswith("file://") else url

    def get(self, rel: str, dest: str) -> bool:
        path = os.path.join(self.root, rel)
        if not os.path.isfile(path):
            return False
        shutil.copyfile(path, dest)
        return True

    def put(self, src: str, rel: str) -> None:
        path = os.path.join(self.root, rel)
        tmp = ""
        old = os.umask(0o002)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".put-", dir=os.path.dirname(path))
            os.close(fd)
            shutil.copyfile(src, tmp)
            os.chmod(tmp, 0o664)
            os.replace(tmp, path)
        except OSError as e:
            if tmp:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
            raise StoreError(f"{self.url}: {e.strerror or e}") from None
        finally:
            os.umask(old)

    def list(self, rel: str) -> list[str]:
        try:
            return sorted(os.listdir(os.path.join(self.root, rel)))
        except OSError:
            return []


def default_url(driver) -> str:
    return f"file://{driver.get('HOME')}/.cache/scbi/binaries"


def configured(driver) -> list[tuple[str, str]]:
    """The (url, mode) of the stores of the run."""
    value = driver.get("SCBI_BINARY_STORE")
    run = driver.get("DO_BINARY_STORE")
    if run == "no" or value == "no":
        return []
    if not value:
        old = driver.get("SCBI_CACHE_DIR")
        if old == "no":
            return []
        value = f"file://{old}" if old else default_url(driver)
    out = []
    extra = driver.get("BINARY_STORE_URL")
    for item in ([extra] if extra else []) + words(value):
        mode = "rw"
        if item.startswith("ro:"):
            mode, item = "ro", item[len("ro:"):]
        if run == "pull":
            mode = "ro"
        out.append((item, mode))
    return out


def make(url: str, mode: str) -> Store | None:
    """The store of a URL, None when its transport is not supported."""
    if url.startswith("file://") or url.startswith("/"):
        return FileStore(url, mode)
    return None


def stores(driver) -> list[Store]:
    """The stores of the run (the unsupported URLs reported once)."""
    cached = getattr(driver, "_binary_stores", None)
    if cached is not None:
        return cached
    out = []
    for url, mode in configured(driver):
        store = make(url, mode)
        if store is None:
            driver.log.ilog("build", f"warning: binary store {url}: unsupported transport, not used")
            continue
        out.append(store)
    driver._binary_stores = out
    return out
