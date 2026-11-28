"""--check-deps: undeclared dependencies of a module.

After a module is built, the files its build used are compared with the
files installed by the other modules of the sandbox: a file of a module
which is not a dependency of the built module (directly or not: depends,
build-depends, modules of meta-modules) is reported. Such a dependency
works by chance (the module happens to be installed in the global
prefix) and breaks on another machine or in another build order.

The files used are found in:

- the dependency files of the compilers in the build tree (``*.d``,
  ``.deps/*.Po``... written by gcc/clang -MD, automake, CMake with
  Makefiles), and the dependencies recorded by Ninja (``ninja -t deps``,
  CMake and Meson);
- the shared libraries needed by the ELF files installed (``readelf -d``),
  when no library of the system has the same name.

This is a heuristic: a file is only reported when another module of the
sandbox installed it. It never changes the build, it reports (a warning,
an error with --check-deps:error).
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess

from scbi.bashcompat import words
from scbi.modref import strip_host

#  dependency files of the compilers and build tools
_DEPFILE = re.compile(r".*\.(d|Po|Plo|Tpo)$|^(compiler_)?depend\.make$")
#  the system library directories (a library found there is not reported)
_SYSTEM_LIBDIRS = ("/lib", "/lib64", "/usr/lib", "/usr/lib64", "/usr/local/lib")
#  number of files listed per module in a report
_SHOWN = 3


def _tool(driver, *names: str) -> str | None:
    for n in names:
        path = driver.which(n)
        if path:
            return path
    return None


# ---------------------------------------------------------- the modules


def allowed_modules(builder, formodule: str, modref: str) -> set[str]:
    """The module and all its dependencies (recursively, meta-modules and
    their modules included; not the testsuite ones)."""
    from scbi.walker import Walker

    d = builder.d
    found: set[str] = set()

    def callback(argv: list[str]) -> None:
        if len(argv) < 6 or argv[-3] == "true":
            return
        info = d.plan.module_ref(strip_host(" ".join(argv[1:-5])), argv[0]) + [""]
        found.add(info[0])

    Walker(builder).walk("for-all-modules-with-meta-ext", callback, modref, name="check-deps-callback")
    found.add((d.plan.module_ref(modref, formodule) + [""])[0])
    return found


def _walk_install(root: str) -> list[str]:
    """Paths (files and links) of an install tree, relative to it."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        for name in filenames + [n for n in dirnames if os.path.islink(os.path.join(dirpath, n))]:
            out.append(os.path.normpath(os.path.join(rel, name)))
    return out


class Owners:
    """The files installed by the modules of the sandbox: in their install
    directory in the sandbox and in their global install directory."""

    def __init__(self, driver):
        self.files: dict[str, set[str]] = {}
        self.names: dict[str, set[str]] = {}
        self.roots: set[str] = set()
        bdir, target = driver.get("SCBI_BDIR"), driver.get("SCBI_TARGET")
        try:
            modules = sorted(os.listdir(bdir))
        except OSError:
            modules = []
        for module in modules:
            idfile = os.path.join(bdir, module, f"install-{target}-id")
            installs: list[tuple[str, str]] = []
            try:
                with open(idfile, errors="surrogateescape") as f:
                    lines = f.read().splitlines()
                variant, idir = (lines + ["", ""])[:2]
                tv = os.path.join(bdir, module, f"{target}-{variant}", "install")
                installs.append((tv, tv))
                if idir and idir.upper() != "NONE":
                    installs.append((tv, idir))
            except OSError:
                #  not installed globally (prefix NONE...): its sandbox
                #  installation still counts
                for tv in glob.glob(os.path.join(bdir, module, f"{target}-*", "install")):
                    installs.append((tv, tv))
            for tree, base in installs:
                if not os.path.isdir(tree):
                    continue
                bases = {os.path.normpath(base), os.path.realpath(base)}
                self.roots |= bases
                for rel in _walk_install(tree):
                    for b in bases:
                        self.files.setdefault(os.path.join(b, rel), set()).add(module)
                    self.names.setdefault(os.path.basename(rel), set()).add(module)

    def owners(self, path: str) -> set[str]:
        path = os.path.normpath(path)
        own = self.files.get(path)
        if own is None and any(path.startswith(r + "/") for r in self.roots):
            own = self.files.get(os.path.realpath(path))
        return own or set()


# -------------------------------------------------------- the files used


def _make_deps(text: str) -> list[str]:
    """The absolute paths of a Makefile dependency file."""
    text = text.replace("\\\n", " ")
    out = []
    for token in text.split():
        if token.endswith(":"):
            continue
        if token.startswith("/"):
            out.append(token)
    return out


def used_files(driver, build_dir: str) -> list[str]:
    """The files used by the build: the dependencies recorded in the
    target directory of the module (its install and logs excluded)."""
    used: list[str] = []
    ninja_dirs = []
    for dirpath, dirnames, filenames in os.walk(build_dir):
        #  the installation and the logs of the module are not its build
        dirnames[:] = [n for n in dirnames if not (dirpath == build_dir and n in ("install", "logs"))]
        if ".ninja_deps" in filenames:
            ninja_dirs.append(dirpath)
        for name in filenames:
            if _DEPFILE.match(name):
                try:
                    with open(os.path.join(dirpath, name), errors="surrogateescape") as f:
                        used += _make_deps(f.read())
                except OSError:
                    pass
    ninja = _tool(driver, "ninja", "samu") if ninja_dirs else None
    for nd in ninja_dirs if ninja else []:
        proc = subprocess.run([ninja, "-C", nd, "-t", "deps"], capture_output=True,
                              env=driver.base_env(), stdin=subprocess.DEVNULL)
        for line in proc.stdout.decode(errors="surrogateescape").splitlines():
            #  "target: #deps N, ..." then the dependencies indented
            if line.startswith((" ", "\t")):
                p = line.strip()
                used.append(p if os.path.isabs(p) else os.path.join(nd, p))
    return used


def _system_libraries(driver) -> set[str]:
    """The names of the shared libraries of the system."""
    names: set[str] = set()
    ldconfig = _tool(driver, "ldconfig") or ("/sbin/ldconfig" if os.path.exists("/sbin/ldconfig") else None)
    if ldconfig:
        proc = subprocess.run([ldconfig, "-p"], capture_output=True, stdin=subprocess.DEVNULL)
        for line in proc.stdout.decode(errors="surrogateescape").splitlines()[1:]:
            name = line.strip().split(" ", 1)[0]
            if name:
                names.add(name)
    for libdir in _SYSTEM_LIBDIRS:
        for d in [libdir, *glob.glob(f"{libdir}/*-linux-gnu*")]:
            try:
                names.update(os.listdir(d))
            except OSError:
                pass
    return names


def needed_libraries(driver, install_dir: str) -> list[str]:
    """The NEEDED entries of the ELF files installed by the module."""
    readelf = _tool(driver, "readelf")
    if readelf is None or not os.path.isdir(install_dir):
        return []
    elfs = []
    for dirpath, _dirnames, filenames in os.walk(install_dir):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            try:
                with open(path, "rb") as f:
                    if f.read(4) == b"\x7fELF":
                        elfs.append(path)
            except OSError:
                pass
    needed: list[str] = []
    for i in range(0, len(elfs), 100):
        proc = subprocess.run([readelf, "-d", "-W", *elfs[i:i + 100]], capture_output=True,
                              env=dict(driver.base_env(), LANG="C", LC_ALL="C"), stdin=subprocess.DEVNULL)
        needed += re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]",
                             proc.stdout.decode(errors="surrogateescape"))
    return needed


# ------------------------------------------------------------------ check


def check(builder, formodule: str, modref: str, module: str, tvdir: str) -> int:
    """Reports the undeclared dependencies of the module just built;
    returns 1 when some are found and --check-deps:error is set."""
    d = builder.d
    allowed = allowed_modules(builder, formodule, modref)
    owners = Owners(d)
    found: dict[str, list[str]] = {}

    def report(owned: set[str], what: str) -> None:
        if not owned or owned & allowed:
            return
        for m in sorted(owned):
            if what not in found.setdefault(m, []):
                found[m].append(what)

    #  the build tree: build (out of tree) or src
    if os.path.isdir(tvdir):
        for path in sorted(set(used_files(d, tvdir))):
            report(owners.owners(path), _short(d, path))

    needed = sorted(set(needed_libraries(d, os.path.join(tvdir, "install"))))
    if needed:
        system = _system_libraries(d)
        own_install = {os.path.basename(p) for p in _walk_install(os.path.join(tvdir, "install"))}
        for lib in needed:
            if lib in system or lib in own_install:
                continue
            report(owners.names.get(lib, set()), lib)

    if not found:
        return 0
    error = d.get("DO_CHECK_DEPS") == "error"
    log = builder.elog if error else builder.ilog
    for m in sorted(found):
        files = found[m]
        shown = ", ".join(files[:_SHOWN]) + (f" (+{len(files) - _SHOWN} more)" if len(files) > _SHOWN else "")
        log(module, *words(f"{'error' if error else 'warning'}: uses {m}, not a dependency:"), shown)
    return 1 if error else 0


def _short(driver, path: str) -> str:
    """A path for the report: the sandbox and the prefix shortened."""
    for var, label in (("SCBI_BDIR", "<sandbox>"), ("SCBI_PREFIX", "<prefix>")):
        v = driver.get(var)
        if v and path.startswith(v + "/"):
            return label + path[len(v):]
    return path
