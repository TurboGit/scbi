"""The binary store during a build (scbi.build, module_subshell).

For a module to build: its binary keys are computed (relocatable Kr and
bound Kb) from its build id, the binary keys of its direct dependencies
(``<tvdir>/binary-key`` of each, written when it was built or installed),
its environment, the OS... The stores are looked up in order, Kr then Kb.
A hit is installed (relocated) instead of building, and copied into the
writable stores before the one it was found in. After a build, the
installation is written to the writable stores: under Kr when it can be
relocated, under Kb otherwise.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile

from scbi.binstore import blob, key, relocate, stores

KEY_FILE = "binary-key"


def entry_path(target: str, module: str, name: str) -> str:
    return f"{target}/{module}/{name}"


def enabled(driver) -> bool:
    return bool(stores.stores(driver))


#  a reference of a plug-in to the build or source tree of a module
_TREE_REF = re.compile(r"module-dir\s+([A-Za-z0-9_.+-]+)\s+(?:build|src)\b|\[([A-Za-z0-9_.+-]+)@(?:build|src)\]")


def tree_users(driver) -> dict[str, set[str]]:
    """The modules whose build or source tree a plug-in uses (module-dir
    <m> build, SCBI_MODULES_DIR[<m>@build]...) -> the plug-ins using it.
    Their installation alone is not enough: they are always built."""
    cached = getattr(driver, "_binary_tree_users", None)
    if cached is not None:
        return cached
    from scbi.plugin import formats

    users: dict[str, set[str]] = {}
    plugins = driver.get("SCBI_PLUGINS")
    try:
        names = sorted(os.listdir(plugins))
    except OSError:
        names = []
    for name in names:
        if formats.format_of(name) is None:
            continue
        try:
            with open(os.path.join(plugins, name), errors="surrogateescape") as f:
                text = f.read()
        except OSError:
            continue
        for m in _TREE_REF.finditer(text):
            users.setdefault(m.group(1) or m.group(2), set()).add(name.rsplit(".", 1)[0])
    driver._binary_tree_users = users
    return users


class Session:
    def __init__(self, builder, formodule: str, modref: str, module: str, variant: str, ref: str,
                 tvdir: str):
        self.b = builder
        self.d = builder.d
        self.formodule = formodule
        self.modref = modref
        self.module = module
        self.variant = variant
        self.ref = ref
        self.tvdir = tvdir
        self.comps: dict | None = None
        self.kr = self.kb = ""
        self.reason = ""
        #  the hit: (index of the store, metadata, tarball)
        self.hit: tuple[int, dict, str] | None = None
        self.work = ""

    # ------------------------------------------------------------ keys

    def depends_keys(self) -> dict[str, str] | None:
        """The binary keys of the direct dependencies (the modules of a
        meta-module); None when one is not known."""
        from scbi.errors import Exit
        from scbi.walker import Walker

        d, b = self.d, self.b
        is_meta = d.registry.loaded.get(f"{self.module}.{self.variant}") == "meta"
        max_level = 0 if is_meta else 1
        found: dict[str, str] = {}
        missing: list[str] = []

        def callback(argv: list[str]) -> None:
            a = (argv + [""] * 7)[:7]
            formodule, ref, level, _kind, is_ext, meta = a[:6]
            if _int(level) < max_level or meta == "true" or is_ext == "true":
                return
            m, v = (d.plan.module_ref(ref, formodule) + ["", ""])[:2]
            path = (b.host_dir(m, v, KEY_FILE) if b.is_host_dep(ref)
                    else os.path.join(b.target_dir(m, v), KEY_FILE))
            try:
                with open(path) as f:
                    found[("host@" if b.is_host_dep(ref) else "") + m] = f.read().strip()
            except OSError:
                missing.append(m)

        try:
            Walker(b).walk("for-all-direct-modules-with-meta-ext", callback, self.modref,
                           name="binary-key-callback")
        except Exit:
            return None
        if missing:
            self.reason = f"no binary key for {', '.join(sorted(set(missing)))}"
            return None
        return found

    def compute(self) -> bool:
        """The keys of the build (its environment is the one of the module,
        set by the caller); False when they cannot be known."""
        from scbi.steps.hookenv import hook_environment

        d = self.d
        try:
            with open(os.path.join(d.get("SCBI_BDIR"), self.module, f"build-id-{self.variant}")) as f:
                build_id = f.read().strip()
        except OSError:
            self.reason = "no build id"
            return False
        deps = self.depends_keys()
        if deps is None:
            return False
        env = hook_environment(d.sv.environ(), d.environ, d.envfile.passthrough)
        extra = ""
        hook = d.envfile.hook("binary_key")
        if hook is not None:
            status, extra = hook(self.module, self.variant, d.get("SCBI_TARGET"))
            if status != 0:
                self.reason = f"binary-key failed with status {status}"
                return False
        self.comps = key.components(d, build_id, deps, env, extra)
        self.kr, self.kb = key.keys(d, self.comps)
        return True

    def record(self) -> None:
        """The key of the build, for the modules depending on it, and its
        components (scbi binary-store --show-key)."""
        if self.kr:
            with open(os.path.join(self.tvdir, KEY_FILE), "w") as f:
                f.write(self.kr + "\n")
            if self.comps is not None:
                with open(os.path.join(self.tvdir, f"{KEY_FILE}.json"), "w") as f:
                    json.dump(self.comps, f, indent=1, sort_keys=True)

    # ---------------------------------------------------------- lookup

    def _workdir(self) -> str:
        if not self.work:
            os.makedirs(self.tvdir, exist_ok=True)
            self.work = tempfile.mkdtemp(prefix=".binstore-", dir=self.tvdir)
        return self.work

    def cleanup(self) -> None:
        if self.work:
            shutil.rmtree(self.work, ignore_errors=True)
            self.work = ""

    def lookup(self) -> bool:
        """Finds the entry of the build in the stores (downloaded in a
        temporary directory)."""
        target = self.d.get("SCBI_TARGET")
        work = self._workdir()
        for i, store in enumerate(stores.stores(self.d)):
            for k in (self.kr, self.kb):
                mpath = os.path.join(work, f"{k}.json")
                try:
                    if not store.get(entry_path(target, self.module, f"{k}.json"), mpath):
                        continue
                    with open(mpath) as f:
                        meta = json.load(f)
                    if meta.get("key") != k:
                        continue
                    name = f"{k}.tar.{meta['tarball']['compression']}"
                    tpath = os.path.join(work, name)
                    if not store.get(entry_path(target, self.module, name), tpath):
                        continue
                except (OSError, ValueError, KeyError, stores.StoreError) as e:
                    self.b.ilog(self.module, f"warning: binary store {store.url}: {e}")
                    continue
                self.hit = (i, meta, tpath)
                return True
        return False

    def install(self) -> bool:
        """Installs the entry found; False (a warning, nothing installed)
        on a failure."""
        assert self.hit is not None
        i, meta, tarball = self.hit
        try:
            blob.unpack(self.d, meta, tarball, self.tvdir, blob.roots(self.d))
        except (blob.BlobError, relocate.RelocationError, OSError) as e:
            shutil.rmtree(os.path.join(self.tvdir, "install"), ignore_errors=True)
            self.b.ilog(self.module, f"warning: binary store {stores.stores(self.d)[i].url}: {e}, building")
            return False
        #  copied into the writable stores before the one of the hit
        self._put(stores.stores(self.d)[:i], meta, tarball)
        self.record()
        return True

    @property
    def store_name(self) -> str:
        assert self.hit is not None
        return stores.stores(self.d)[self.hit[0]].url

    # ---------------------------------------------------------- upload

    def upload(self) -> None:
        """Writes the installation just built to the writable stores (a
        warning on a failure)."""
        targets = [s for s in stores.stores(self.d) if s.writable]
        self.record()
        if not targets or not self.comps or not os.path.isdir(os.path.join(self.tvdir, "install")):
            #  nothing installed: nothing to reuse
            return
        d = self.d
        mdir = os.path.join(d.get("SCBI_BDIR"), self.module)
        roots = blob.roots(d)
        try:
            tarball, extra = blob.pack(d, self.tvdir, {
                "source-ref": os.path.join(mdir, "source-ref"),
                "build-id": os.path.join(self.tvdir, "build-id"),
                "build-deps": os.path.join(self.tvdir, "build-deps"),
            }, os.path.join(self.tvdir, "logs"), list(roots.values()), self._workdir())
        except (blob.BlobError, OSError) as e:
            self.b.ilog(self.module, f"warning: binary store: {e}")
            return
        relocatable = extra["relocatable"]
        k = self.kr if relocatable else self.kb
        comps = self.comps if relocatable else dict(self.comps, location=key.location(d))
        meta = blob.metadata(d, k, "relocatable" if relocatable else "bound", comps, self.module,
                             self.variant, self.ref, tarball, extra, roots)
        self._put(targets, meta, tarball)

    def _better(self, store, meta: dict) -> bool:
        """Whether to write the entry to the store: not there yet, or there
        with a shorter origin path (the entry relocatable to the most
        sandboxes is kept: a path is relocated in a binary file only to a
        path not longer)."""
        target = self.d.get("SCBI_TARGET")
        path = os.path.join(self._workdir(), "existing.json")
        try:
            if not store.get(entry_path(target, self.module, f"{meta['key']}.json"), path):
                return True
            with open(path) as f:
                old = json.load(f)
        except (OSError, ValueError, stores.StoreError):
            return True
        return meta["kind"] == "relocatable" and _origin_length(meta) > _origin_length(old)

    def _put(self, targets, meta: dict, tarball: str) -> None:
        target = self.d.get("SCBI_TARGET")
        k = meta["key"]
        jpath = os.path.join(self._workdir(), f"put-{k}.json")
        with open(jpath, "wb") as f:
            f.write(blob.dumps(meta))
        for store in targets:
            if not store.writable:
                continue
            if not self._better(store, meta):
                continue
            try:
                #  the tarball first: an entry is complete when its JSON is there
                store.put(tarball, entry_path(target, self.module, f"{k}.tar.{meta['tarball']['compression']}"))
                store.put(jpath, entry_path(target, self.module, f"{k}.json"))
            except stores.StoreError as e:
                self.b.ilog(self.module, f"warning: binary store: {e}")


def _origin_length(meta: dict) -> int:
    return max((len(p) for p in meta.get("origin", {}).values()), default=0)


def record_meta(builder, meta: str, variant: str, tvdir: str) -> None:
    """The binary key of a meta-module: its build id and the binary keys
    of its modules (none when one is not known), for the modules depending
    on it."""
    d = builder.d
    for name in (KEY_FILE, f"{KEY_FILE}.json"):
        try:
            os.unlink(os.path.join(tvdir, name))
        except OSError:
            pass
    session = Session(builder, "@root", meta, meta, variant, "", tvdir)
    try:
        with open(os.path.join(d.get("SCBI_BDIR"), meta, f"build-id-{variant}")) as f:
            build_id = f.read().strip()
    except OSError:
        return
    deps = session.depends_keys()
    if deps is None:
        return
    session.kr = key.digest({"format": key.FORMAT, "meta": build_id, "depends": dict(sorted(deps.items()))})
    session.record()


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0
