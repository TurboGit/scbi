"""The binary stores: an ordered list of stores, each a URL with a mode
(rw, the default, or ro).

The list, the first set of:

- SCBI_BINARY_STORE: the URLs separated by blanks, ``ro:<url>`` read-only;
  ``no``: no store;
- the ``binary-stores`` key of the environment file;
- SCBI_CACHE_DIR (the former build cache);
- ``file://$HOME/.cache/scbi/binaries``.

For a run: --binary-store=<url> adds a store first, --binary-store:pull
reads only, --binary-store:no uses none.

A store gives the files of its entries by path (``<target>/<module>/
<key>.json``...): ``get`` (copy to a local file), ``put`` and ``list``.

- file:// or a path: a directory (a local disk or a NFS mount), atomic
  writes;
- http://, https://: GET and PUT with curl (credentials of ~/.netrc,
  options SCBI_BINARY_STORE_CURL_OPTIONS), list from the directory index
  of the server;
- another scheme: the functions binary-store-get URL PATH DEST,
  binary-store-put URL FILE PATH and binary-store-list URL DIR of the
  environment file.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import subprocess
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

    def delete(self, rel: str) -> None:
        """Removes the file ``rel`` (nothing when it is not there)."""
        raise StoreError(f"{self.url}: cannot remove files")

    def last_used(self, rel: str) -> float | None:
        """The time the file was last used (written or read), None when the
        store does not know it."""
        return None

    def touch(self, rel: str) -> None:
        """Records that the file is used (the least recently used entries
        are removed first by --gc)."""


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

    def delete(self, rel: str) -> None:
        try:
            os.unlink(os.path.join(self.root, rel))
        except FileNotFoundError:
            pass
        except OSError as e:
            raise StoreError(f"{self.url}: {e.strerror or e}") from None

    def last_used(self, rel: str) -> float | None:
        try:
            return os.stat(os.path.join(self.root, rel)).st_mtime
        except OSError:
            return None

    def touch(self, rel: str) -> None:
        with contextlib.suppress(OSError):
            os.utime(os.path.join(self.root, rel))


class HttpStore(Store):
    """A Web server: GET, and PUT to write (WebDAV, nginx dav, Artifactory:
    the server creates the directories)."""

    scheme = "http"

    def __init__(self, url: str, mode: str, driver):
        super().__init__(url.rstrip("/"), mode)
        self.d = driver
        self.curl = driver.which("curl")

    def _curl(self, *args: str) -> subprocess.CompletedProcess:
        if self.curl is None:
            raise StoreError(f"{self.url}: curl not found")
        return subprocess.run([self.curl, "-f", "-s", "-S", "-L", "--netrc-optional",
                               *words(self.d.get("SCBI_BINARY_STORE_CURL_OPTIONS")), *args],
                              capture_output=True, env=self.d.base_env(), stdin=subprocess.DEVNULL)

    def get(self, rel: str, dest: str) -> bool:
        proc = self._curl("-o", dest, f"{self.url}/{rel}")
        if proc.returncode == 0:
            return True
        with contextlib.suppress(OSError):
            os.unlink(dest)
        #  22: an HTTP error (404: not there)
        if proc.returncode == 22:
            return False
        raise StoreError(f"{self.url}: {proc.stderr.decode(errors='replace').strip()}")

    def put(self, src: str, rel: str) -> None:
        proc = self._curl("-T", src, f"{self.url}/{rel}")
        if proc.returncode != 0:
            raise StoreError(f"{self.url}: {proc.stderr.decode(errors='replace').strip()}")

    def list(self, rel: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            page = os.path.join(tmp, "index.html")
            try:
                if not self.get(rel.rstrip("/") + "/", page):
                    return []
            except StoreError:
                return []
            with open(page, errors="replace") as f:
                text = f.read()
        names = {os.path.basename(h.rstrip("/")) for h in re.findall(r'href="([^"?#]+)"', text)}
        return sorted(n for n in names if n and not n.startswith("."))

    def delete(self, rel: str) -> None:
        proc = self._curl("-X", "DELETE", "-o", os.devnull, f"{self.url}/{rel}")
        if proc.returncode not in (0, 22):
            raise StoreError(f"{self.url}: {proc.stderr.decode(errors='replace').strip()}")


class FunctionStore(Store):
    """A store whose transport is given by the functions of the
    environment file (binary-store-get/put/list)."""

    def __init__(self, url: str, mode: str, driver):
        super().__init__(url, mode)
        self.d = driver

    def _hook(self, name: str):
        hook = self.d.envfile.hook(name)
        if hook is None:
            raise StoreError(f"{self.url}: no function {name.replace('_', '-')} in the environment file")
        return hook

    def get(self, rel: str, dest: str) -> bool:
        status = self._hook("binary_store_get")(self.url, rel, dest)
        if status == 0 and os.path.isfile(dest):
            return True
        if status in (0, 1):
            return False
        raise StoreError(f"{self.url}: binary-store-get {rel} failed with status {status}")

    def put(self, src: str, rel: str) -> None:
        status = self._hook("binary_store_put")(self.url, src, rel)
        if status != 0:
            raise StoreError(f"{self.url}: binary-store-put {rel} failed with status {status}")

    def list(self, rel: str) -> list[str]:
        hook = self.d.envfile.hook("binary_store_list")
        if hook is None:
            return []
        status, out = hook(self.url, rel)
        return sorted(n for n in out.split() if n) if status == 0 else []

    def delete(self, rel: str) -> None:
        status = self._hook("binary_store_delete")(self.url, rel)
        if status not in (0, 1):
            raise StoreError(f"{self.url}: binary-store-delete {rel} failed with status {status}")


def default_url(driver) -> str:
    return f"file://{driver.get('HOME')}/.cache/scbi/binaries"


def configured(driver) -> list[tuple[str, str]]:
    """The (url, mode) of the stores of the run."""
    value = driver.get("SCBI_BINARY_STORE")
    run = driver.get("DO_BINARY_STORE")
    if run == "no" or value == "no":
        return []
    items: list[tuple[str, str]] = []
    if value:
        for item in words(value):
            items.append((item[len("ro:"):], "ro") if item.startswith("ro:") else (item, "rw"))
    elif getattr(driver.envfile, "binary_stores", None) is not None:
        items = list(driver.envfile.binary_stores)
    else:
        old = driver.get("SCBI_CACHE_DIR")
        if old == "no":
            items = []
        else:
            items = [(f"file://{old}" if old else default_url(driver), "rw")]
    extra = driver.get("BINARY_STORE_URL")
    if extra:
        items.insert(0, (extra, "rw"))
    return [(url, "ro" if run == "pull" else mode) for url, mode in items]


def make(url: str, mode: str, driver=None) -> Store | None:
    """The store of a URL, None when its transport is not supported."""
    if url.startswith("file://") or url.startswith("/"):
        return FileStore(url, mode)
    if driver is not None and url.startswith(("http://", "https://")):
        return HttpStore(url, mode, driver)
    if driver is not None and driver.envfile.hook("binary_store_get") is not None:
        return FunctionStore(url, mode, driver)
    return None


def stores(driver) -> list[Store]:
    """The stores of the run (the unsupported URLs reported once)."""
    cached = getattr(driver, "_binary_stores", None)
    if cached is not None:
        return cached
    out = []
    for url, mode in configured(driver):
        store = make(url, mode, driver)
        if store is None:
            driver.log.ilog("build", f"warning: binary store {url}: unsupported transport, not used")
            continue
        out.append(store)
    driver._binary_stores = out
    return out
