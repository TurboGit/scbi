"""--check-deps: the undeclared and the unused dependencies of a module.

After a module is built, the files its build used are compared with the
files installed by the modules of the sandbox:

- a file of a module which is not a dependency of the built module
  (directly or not: depends, build-depends, tests-depends, modules of
  meta-modules) is reported: such a dependency works by chance (the module
  happens to be installed in the global prefix) and breaks on another
  machine or in another build order (a warning, an error with
  --check-deps:error);
- a direct dependency (depends, build-depends) none of whose files is
  used, nor the files of its own dependencies, is reported as possibly
  unused (a note, never an error).

The files used are found in:

- the dependency files of the compilers in the build tree (``*.d``,
  ``.deps/*.Po``... written by gcc/clang -MD, automake, CMake with
  Makefiles), and the dependencies recorded by Ninja (``ninja -t deps``,
  CMake and Meson);
- the shared libraries needed by the ELF files installed (``readelf -d``),
  when no library of the system has the same name;
- for a Python module (pyproject.toml, setup.py or setup.cfg in its
  sources), the top-level modules imported by its Python files (an import
  in a try block is optional: used, never reported as undeclared);
- with --check-deps:trace, the files opened and the programs run by the
  commands of the steps (config, build, install, tests), recorded with
  strace: complete (tools, pkg-config files, data, Python imports), but
  slower.

A heuristic: only the files installed by modules of the sandbox count; a
module with no evidence at all (no dependency file, no ELF file, no Python
file, no trace) is not checked for unused dependencies, nor is a
dependency installing neither headers nor libraries, or adding to PATH
in its env hook (a tool), without trace. It never changes the build.
"""

from __future__ import annotations

import ast
import glob
import os
import re
import shutil
import subprocess

from scbi.bashcompat import words
from scbi.modref import is_host_prefixed, strip_host

#  dependency files of the compilers and build tools
_DEPFILE = re.compile(r".*\.(d|Po|Plo|Tpo)$|^(compiler_)?depend\.make$")
#  the system library directories (a library found there is not reported)
_SYSTEM_LIBDIRS = ("/lib", "/lib64", "/usr/lib", "/usr/lib64", "/usr/local/lib")
#  number of files listed per module in a report
_SHOWN = 3
#  the markers of a Python module
_PY_PROJECT = ("pyproject.toml", "setup.py", "setup.cfg")
#  directories of a Python source tree not scanned
_PY_SKIP = {"build", "dist", "__pycache__", "node_modules", "venv", ".venv", ".tox", ".git"}
#  the steps traced (not setup: the copy of the sources)
TRACED_STEPS = ("config", "build", "install", "tests")
_TRACE_CALLS = "open,openat,openat2,execve,execveat"
_TRACE_LINE = re.compile(r'^(open|openat|openat2|execve|execveat)\((?:AT_FDCWD, |\d+, )?"((?:[^"\\]|\\.)*)"')


def _tool(driver, *names: str) -> str | None:
    for n in names:
        path = driver.which(n)
        if path:
            return path
    return None


# ---------------------------------------------------------- the modules


def _closure(builder, modref: str) -> set[str]:
    """The module of ``modref`` and its dependencies (recursively,
    meta-modules and their modules included; not the testsuite ones)."""
    from scbi.walker import Walker

    d = builder.d
    found: set[str] = set()

    def callback(argv: list[str]) -> None:
        if len(argv) < 6 or argv[-3] == "true":
            return
        info = d.plan.module_ref(strip_host(" ".join(argv[1:-5])), argv[0]) + [""]
        found.add(info[0])

    Walker(builder).walk("for-all-modules-with-meta-ext", callback, modref, name="check-deps-callback")
    return found


def allowed_modules(builder, formodule: str, modref: str) -> set[str]:
    """The module, all its dependencies and the ones of its testsuite."""
    d = builder.d
    module, variant = (d.plan.module_ref(modref, formodule) + ["", ""])[:2]
    found = _closure(builder, modref) | {module}
    for dmodule in builder.get_all_depends(module, variant, "tests-depends"):
        if d.registry.plugin_file(strip_host(dmodule)) is not None:
            found |= _closure(builder, strip_host(dmodule))
    return found


def direct_depends(builder, module: str, variant: str) -> list[str]:
    """The plug-ins of the depends and build-depends hooks (not the host@
    ones: their build is for the host)."""
    d = builder.d
    out: list[str] = []
    for hook in ("build-depends", "depends"):
        for dmodule in builder.get_all_depends(module, variant, hook):
            if is_host_prefixed(dmodule) or d.registry.plugin_file(dmodule) is None:
                continue
            if dmodule not in out:
                out.append(dmodule)
    return out


def provides_tool(driver, module: str, variant: str) -> bool:
    """The env hook of the module changes PATH: it provides a tool to the
    modules depending on it (only seen by a trace)."""
    from scbi.plugin.model import EnvOp, EnvOps
    from scbi.plugin.resolved import _hook_body

    try:
        body = _hook_body(driver, module, variant or "default", "", "", "env")
    except Exception:  # noqa: BLE001 - not known: not a tool
        return False

    def sets_path(ops) -> bool:
        for op in ops:
            if isinstance(op, EnvOp):
                if "PATH" in op.args[:2]:
                    return True
            elif sets_path(getattr(op, "items", ())):
                return True
        return False

    return isinstance(body, EnvOps) and sets_path(body.ops)


def _walk_install(root: str) -> list[str]:
    """Paths (files and links) of an install tree, relative to it."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        for name in filenames + [n for n in dirnames if os.path.islink(os.path.join(dirpath, n))]:
            out.append(os.path.normpath(os.path.join(rel, name)))
    return out


def _python_name(rel: str) -> str | None:
    """The top-level Python module of an installed path
    (.../site-packages/<name>/..., <name>.py, <name>*.so)."""
    parts = rel.split(os.sep)
    for i, p in enumerate(parts[:-1]):
        if p in ("site-packages", "dist-packages"):
            top = parts[i + 1]
            if top == "__pycache__" or top.endswith((".dist-info", ".egg-info", ".pth")):
                return None
            if i + 2 < len(parts):
                return top
            if top.endswith(".py"):
                return top[:-3]
            if top.endswith((".so", ".pyd")):
                return top.split(".", 1)[0]
            return None
    return None


class Owners:
    """The files installed by the modules of the sandbox: in their install
    directory in the sandbox and in their global install directory."""

    def __init__(self, driver):
        self.files: dict[str, set[str]] = {}
        self.names: dict[str, set[str]] = {}
        self.python: dict[str, set[str]] = {}
        #  modules installing headers or libraries (Python modules too)
        self.dev: set[str] = set()
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
            seen: set[str] = set()
            for tree, base in installs:
                if not os.path.isdir(tree):
                    continue
                bases = {os.path.normpath(base), os.path.realpath(base)}
                self.roots |= bases
                rels = _walk_install(tree)
                for rel in rels:
                    for b in bases:
                        self.files.setdefault(os.path.join(b, rel), set()).add(module)
                    if tree in seen:
                        continue
                    self.names.setdefault(os.path.basename(rel), set()).add(module)
                    top = rel.split(os.sep, 1)[0]
                    if top == "include" or top.startswith("lib"):
                        self.dev.add(module)
                    py = _python_name(rel)
                    if py:
                        self.python.setdefault(py, set()).add(module)
                seen.add(tree)

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
    return [t for t in text.split() if not t.endswith(":") and t.startswith("/")]


def used_files(driver, build_dir: str) -> tuple[list[str], bool]:
    """The files used by the build: the dependencies recorded in the
    target directory of the module (its install and logs excluded), and
    whether any dependency file was found."""
    used: list[str] = []
    found = False
    ninja_dirs = []
    for dirpath, dirnames, filenames in os.walk(build_dir):
        #  the installation and the logs of the module are not its build
        dirnames[:] = [n for n in dirnames if not (dirpath == build_dir and n in ("install", "logs"))]
        if ".ninja_deps" in filenames:
            ninja_dirs.append(dirpath)
        for name in filenames:
            if _DEPFILE.match(name):
                found = True
                try:
                    with open(os.path.join(dirpath, name), errors="surrogateescape") as f:
                        used += _make_deps(f.read())
                except OSError:
                    pass
    ninja = _tool(driver, "ninja", "samu") if ninja_dirs else None
    for nd in ninja_dirs if ninja else []:
        found = True
        proc = subprocess.run([ninja, "-C", nd, "-t", "deps"], capture_output=True,
                              env=driver.base_env(), stdin=subprocess.DEVNULL)
        for line in proc.stdout.decode(errors="surrogateescape").splitlines():
            #  "target: #deps N, ..." then the dependencies indented
            if line.startswith((" ", "\t")):
                p = line.strip()
                used.append(p if os.path.isabs(p) else os.path.join(nd, p))
    return used, found


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


def needed_libraries(driver, install_dir: str) -> tuple[list[str], bool]:
    """The NEEDED entries of the ELF files installed by the module, and
    whether there is any ELF file."""
    readelf = _tool(driver, "readelf")
    if readelf is None or not os.path.isdir(install_dir):
        return [], False
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
    return needed, bool(elfs)


# --------------------------------------------------------------- Python


class _Imports(ast.NodeVisitor):
    """The top-level modules imported (absolute imports), optional when in
    a try block."""

    def __init__(self) -> None:
        self.required: set[str] = set()
        self.optional: set[str] = set()
        self.in_try = 0

    def _add(self, name: str) -> None:
        top = name.split(".", 1)[0]
        if top:
            (self.optional if self.in_try else self.required).add(top)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if not node.level and node.module:
            self._add(node.module)

    def visit_Try(self, node: ast.Try) -> None:
        self.in_try += 1
        for n in node.body:
            self.visit(n)
        self.in_try -= 1
        for n in node.handlers + node.orelse + node.finalbody:
            self.visit(n)


def python_roots(driver, module: str, tvdir: str) -> list[str]:
    """The source trees of a Python module: its sources and its build
    directory, when they have a pyproject.toml, setup.py or setup.cfg."""
    roots = []
    for d in (os.path.join(driver.get("SCBI_BDIR"), module, "src"), os.path.join(tvdir, "build")):
        real = os.path.realpath(d)
        if os.path.isdir(real) and real not in roots and any(
                os.path.isfile(os.path.join(real, m)) for m in _PY_PROJECT):
            roots.append(real)
    return roots


def python_imports(roots: list[str]) -> tuple[set[str], set[str], bool]:
    """(required, optional, any file) imports of the Python files."""
    v = _Imports()
    found = False
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [n for n in dirnames if n not in _PY_SKIP and not n.startswith(".")]
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    if os.path.getsize(path) > 2_000_000:
                        continue
                    with open(path, "rb") as f:
                        tree = ast.parse(f.read(), filename=path)
                except (OSError, SyntaxError, ValueError):
                    continue
                found = True
                v.visit(tree)
    return v.required, v.optional - v.required, found


# ---------------------------------------------------------------- trace


def trace_dir(tvdir: str) -> str:
    return os.path.join(tvdir, "logs", "trace")


def start_trace(builder, tvdir: str, keep: bool = False) -> bool:
    """--check-deps:trace: the commands of the steps run under strace
    (scbi.hooks.cmdlang.EXEC_WRAPPER), the trace of a previous build
    removed unless ``keep``; False without strace."""
    from scbi.hooks import cmdlang

    strace = _tool(builder.d, "strace")
    if strace is None:
        return False
    tdir = trace_dir(tvdir)
    if not keep:
        shutil.rmtree(tdir, ignore_errors=True)
    os.makedirs(tdir, exist_ok=True)
    prefix = [strace, "-f", "-ff", "-qq", "-z", "-s", "4096", "-e", f"trace={_TRACE_CALLS}",
              "-o", os.path.join(tdir, "t"), "--"]

    def wrapper(argv: list[str], exe: str) -> tuple[list[str], str]:
        return [*prefix, exe, *argv[1:]], strace

    cmdlang.EXEC_WRAPPER = wrapper
    return True


def stop_trace() -> None:
    from scbi.hooks import cmdlang

    cmdlang.EXEC_WRAPPER = None


def traced_files(tvdir: str) -> tuple[list[str], bool]:
    """The absolute paths opened or run successfully by the traced
    commands, and whether the steps were traced (even when no command
    ran: nothing is used then)."""
    tdir = trace_dir(tvdir)
    try:
        names = os.listdir(tdir)
    except OSError:
        return [], False
    out: list[str] = []
    for name in names:
        try:
            with open(os.path.join(tdir, name), errors="surrogateescape") as f:
                for line in f:
                    m = _TRACE_LINE.match(line)
                    if m and m.group(2).startswith("/"):
                        out.append(m.group(2))
        except OSError:
            pass
    return out, True


# ------------------------------------------------------------------ check


def check(builder, formodule: str, modref: str, module: str, variant: str, tvdir: str) -> int:
    """Reports the undeclared and the unused dependencies of the module
    just built; returns 1 when undeclared ones are found and
    --check-deps:error is set."""
    d = builder.d
    mode = d.get("DO_CHECK_DEPS")
    allowed = allowed_modules(builder, formodule, modref)
    owners = Owners(d)
    #  module -> what of it is used (undeclared), modules used at all
    undeclared: dict[str, list[str]] = {}
    used: set[str] = set()
    evidence = False

    def seen(owned: set[str], what: str, report: bool = True) -> None:
        if not owned:
            return
        used.update(owned)
        if not report or owned & allowed:
            return
        for m in sorted(owned):
            if what not in undeclared.setdefault(m, []):
                undeclared[m].append(what)

    #  the build tree: build (out of tree) or src
    paths: list[str] = []
    if os.path.isdir(tvdir):
        files, found = used_files(d, tvdir)
        paths += files
        evidence |= found
    traced = False
    if mode == "trace":
        files, traced = traced_files(tvdir)
        paths += files
        evidence |= traced
    for path in sorted(set(paths)):
        seen(owners.owners(path), _short(d, path))

    needed, found = needed_libraries(d, os.path.join(tvdir, "install"))
    evidence |= found
    if needed:
        system = _system_libraries(d)
        own_install = {os.path.basename(p) for p in _walk_install(os.path.join(tvdir, "install"))}
        for lib in sorted(set(needed)):
            if lib in system or lib in own_install:
                continue
            seen(owners.names.get(lib, set()), lib)

    roots = python_roots(d, module, tvdir)
    if roots:
        required, optional, found = python_imports(roots)
        evidence |= found
        for name in sorted(required):
            seen(owners.python.get(name, set()), f"import {name}")
        for name in sorted(optional):
            seen(owners.python.get(name, set()), f"import {name}", report=False)

    error = mode == "error"
    log = builder.elog if error else builder.ilog
    for m in sorted(undeclared):
        files = undeclared[m]
        shown = ", ".join(files[:_SHOWN]) + (f" (+{len(files) - _SHOWN} more)" if len(files) > _SHOWN else "")
        log(module, *words(f"{'error' if error else 'warning'}: uses {m}, not a dependency:"), shown)

    if evidence:
        for dmodule in direct_depends(builder, module, variant):
            name, dvariant = (d.plan.module_ref(dmodule, modref) + ["", ""])[:2]
            closure = _closure(builder, dmodule) | {name}
            if closure & used:
                continue
            #  a tool (no headers nor libraries, or adding to PATH): only
            #  seen by a trace; a meta-module installs nothing: its modules
            meta = d.registry.loaded.get(f"{name}.{dvariant}") == "meta"
            checkable = bool(closure & owners.dev) if meta else name in owners.dev
            if not traced and (not checkable or provides_tool(d, name, dvariant)):
                continue
            builder.ilog(module, *words(f"note: {name} may not be needed: none of its files used"))

    return 1 if undeclared and error else 0


def _short(driver, path: str) -> str:
    """A path for the report: the sandbox and the prefix shortened."""
    for var, label in (("SCBI_BDIR", "<sandbox>"), ("SCBI_PREFIX", "<prefix>")):
        v = driver.get(var)
        if v and path.startswith(v + "/"):
            return label + path[len(v):]
    return path
