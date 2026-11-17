"""Dependency walker: port of ``_internal_for-all-modules`` and its
``for-all-modules*`` entry points (scripts.d/5_tools), plus the package
queries of scripts.d/6_distpkg it needs (``get-pkg-name``,
``get-pkg-version``).

The callback is a Python callable receiving the argument list the Bash
callback would get, after word splitting: FORMODULE MODREF LEVEL
DEPENDS_KIND IS_EXT IS_META IS_AGG [extra...].

Bash semantics kept on purpose:
- every argument is passed unquoted (an external package alias expanding
  to several packages shifts the callback arguments; an empty aggregate
  mode drops an argument, ``shift 10`` then fails and the extra arguments
  are the whole argument list);
- ``for ...; do walk; done || res=1``: only the status of the last
  iteration counts;
- the checked set is reset by each entry point, the recursion tree
  (SCBI_RECTREE) is global.
"""

from __future__ import annotations

from typing import Callable

from scbi.bashcompat import words
from scbi.errors import Exit

Callback = Callable[[list[str]], int | None]

#  WITH_META WITH_DEPS WITH_EXT DEPTH(None: 99999 or 2 if --deps direct)
#  DEPENDS_KIND, per for-all-modules* entry point
ENTRY_POINTS = {
    "for-all-modules": ("false", "both", "false", None, "default"),
    "for-all-modules-ext": ("false", "both", "true", None, "default"),
    "for-all-modules-with-meta": ("true", "both", "false", None, "default"),
    "for-all-modules-depends-with-meta": ("true", "deps", "false", None, "default"),
    "for-all-modules-with-meta-ext": ("true", "both", "true", None, "default"),
    "for-all-direct-modules-with-meta-ext": ("true", "both", "true", 1, "default"),
    "for-all-modules-build-depends-with-meta": ("true", "build-deps-1", "false", 99999, "build"),
    "for-all-modules-tests-depends-with-meta": ("true", "tests-deps", "false", 999999, "tests"),
}


def array(driver, name: str) -> dict[str, str]:
    entry = driver.sv.arrays.get(name)
    return entry[1] if entry else {}


def get_pkg_name(driver, pkg: str) -> str:
    """Port of ``get-pkg-name``: an ``os@-`` alias is looked up in
    SCBI_ALIAS (echoed unquoted)."""
    if pkg[:4] == "os@-":
        key = pkg[:-4] if pkg.endswith(":[v]") else pkg
        return " ".join(words(array(driver, "SCBI_ALIAS").get(key, "")))
    return pkg


def get_pkg_version(driver, pkg: str) -> str:
    """Port of ``get-pkg-version``."""
    return " ".join(words(array(driver, "SCBI_PKGS").get(get_pkg_name(driver, pkg), "")))


class Walker:
    def __init__(self, builder):
        self.b = builder
        self.d = builder.d
        self.rectree: list[str] = []
        self.checked: set[str] = set()

    # ------------------------------------------------------------ helpers

    def module_info(self, modref: str, formodule: str | None = None) -> list[str]:
        if formodule is None:
            info = self.d.plan.module_ref(modref)
        else:
            info = self.d.plan.module_ref(modref, formodule)
        return (info + [""] * 4)[:4]

    def load_module(self, modref: str) -> bool:
        """Port of ``load-module`` (status: plug-in found)."""
        module, variant = self.module_info(modref)[:2]
        if not self.d.registry.load_module(module):
            return False
        self.b.load_module(module, variant)
        return True

    def aggregate_mode(self, modref: str) -> str:
        """Port of ``is-meta-aggregate-module`` (the result variable is
        left empty when the module is not an aggregate)."""
        module, variant = self.module_info(modref)[:2]
        if not self.d.registry.loaded.get(module):
            self.load_module(modref)
        return self.d.registry.loaded.get(f"{module}.{variant}.agg", "")

    def check_pkg(self, module: str, ref: str) -> int:
        """``check-pkg`` (queries the OS packages, scbi.ospkg)."""
        from scbi import ospkg

        return ospkg.OsPackages(self.d).check_pkg(f"{module}:{ref}", self.b.out)

    # ------------------------------------------------------------ walker

    def walk(self, entry: str, callback: Callback, modref: str, *extra: str, name: str = "callback") -> int:
        """``<entry> CALLBACK MODREF extra...`` (a for-all-modules* entry
        point); returns the status. ``name`` is the name of the callback
        in Bash (it ends in the callback arguments when ``shift 10``
        fails)."""
        with_meta, with_deps, with_ext, depth, kind = ENTRY_POINTS[entry]
        if depth is None:
            depth = 2 if self.d.get("DO_DEPS") == "yes-direct" else 99999
        self.checked = set()
        args = [*words(name), with_meta, with_deps, with_ext, str(depth), "0", kind,
                *words(modref), "@root", "false", *[w for x in extra for w in words(x)]]
        return self._internal(callback, args)

    def _call(self, callback: Callback, argv: list[str]) -> int:
        res = callback(argv)
        return 0 if res is None else res

    def _internal(self, callback: Callback, args: list[str]) -> int:
        #  args: the positional parameters $1... (CALLBACK first)
        a = args + [""] * max(0, 10 - len(args))
        cbname, with_meta, with_deps, with_ext, depth, level, depends_kind, modref, formodule, is_aggregated = a[:10]
        #  shift 10 (fails, nothing shifted, with fewer arguments)
        rest = args[10:] if len(args) >= 10 else list(args)

        is_agg = "false"
        if is_aggregated == "recursive":
            is_agg = "true"
        elif is_aggregated == "direct":
            is_agg = "true"
            is_aggregated = "false"

        r_deps, r_bdeps, r_tdeps = "yes", "yes", "no"
        if with_deps == "deps":
            r_bdeps = "no"
        elif with_deps == "tests-deps":
            r_deps, r_bdeps, r_tdeps = "no", "no", "yes"
        elif with_deps in ("build-deps", "build-deps-1"):
            r_deps = "no"

        if _int(level) > _int(depth):
            return 0

        module, variant, _kind, ref = self.module_info(modref, formodule)
        if ref == "skip":
            return 0

        nextl = str(_int(level) + 1)

        if module in self.rectree:
            log = self.d.log
            log.elog(module, "recursive", "dependencies", "detected")
            tree = self.rectree
            for i in range(len(tree) - 1):
                log.elog(module, f" ⦁ {tree[i]}", "%B%t→%c", *words(tree[i + 1]))
            log.elog(module, f" ⦁ {tree[-1] if tree else ''}", "%B%t→%c", *words(module))
            raise Exit(1)

        is_meta = "false"
        mkey = f"{modref}:{depends_kind}"
        if mkey in self.checked:
            return 0
        self.checked.add(mkey)

        def emit(name: str) -> int:
            return self._call(callback, [*words(formodule), *words(name), *words(level),
                                         *words(depends_kind), *words(ext), *words(is_meta),
                                         *words(is_agg), *[w for x in rest for w in words(x)]])

        if self.load_module(modref):
            ext = "false"
            self.rectree.append(module)
            res = 0
            prefix, target = self.d.get("SCBI_PREFIX"), self.d.get("SCBI_TARGET")
            mods = "\n".join(self.d.runner().variant_values(
                module, variant, "modules", [prefix, target, variant],
                self.d.plan, self.b.modules_list)).strip("\n")
            if mods:
                is_meta = "true"

            def recurse(items: list[str]) -> int:
                status = 0
                for item in items:
                    status = self._internal(callback, item)
                return status

            if with_meta == "true" and is_meta == "true":
                nxl = nextl if self.d.get("DO_DEPS") == "yes-direct" else level
                amode = self.aggregate_mode(modref)
                if recurse([[cbname, with_meta, with_deps, with_ext, depth, nxl, depends_kind,
                             dmodule, module, *words(amode), *rest]
                            for dmodule in words(mods)]) != 0:
                    res = 1
                if res == 0:
                    emit(modref)
                self.rectree.pop()
                return res

            if r_deps == "yes":
                if recurse([[cbname, with_meta, with_deps, with_ext, depth, nextl, "default",
                             dmodule, module, *words(is_aggregated), *rest]
                            for dmodule in self.b.get_all_depends(module, variant, "depends")]) != 0:
                    res = 1

            if res == 0 and r_bdeps == "yes":
                nextd = "deps" if with_deps == "build-deps-1" else with_deps
                if recurse([[cbname, with_meta, nextd, with_ext, depth, nextl, "build",
                             dmodule, module, *words(is_aggregated), *rest]
                            for dmodule in self.b.get_all_depends(module, variant, "build-depends")]) != 0:
                    res = 1

            if res == 0 and r_tdeps == "yes":
                if recurse([[cbname, with_meta, with_deps, with_ext, depth, nextl, "tests",
                             dmodule, module, *words(is_aggregated), *rest]
                            for dmodule in self.b.get_all_depends(module, variant, "tests-depends")]) != 0:
                    res = 1

            if res == 0:
                emit(modref)
            self.rectree.pop()
            return res

        #  not a plug-in: an external dependency
        ext = "true"
        if with_ext == "true":
            pkgname = get_pkg_name(self.d, modref)
            if pkgname:
                emit(pkgname)
        else:
            if self.check_pkg(module, ref) == 1 and self.d.get("DO_WARNING_EXTERNAL") == "no":
                raise Exit(1)
        return 0


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def build_order(builder, modrefs: list[str]) -> list[str]:
    """The modules of the command line in an order where none is a
    dependency (direct or not: dependencies, build dependencies, modules
    of meta-modules) of a module before it: the given order is kept
    except where a module must come later. Used without --deps, the
    dependencies are then not built by the driver. On an error of the
    walk (a recursive dependency...) the given order is returned."""
    d = builder.d
    if len(modrefs) < 2:
        return list(modrefs)

    def name(modref: str, formodule: str = "@root") -> str:
        return (d.plan.module_ref(modref, formodule) + [""])[0]

    names = [name(m) for m in modrefs]
    deps: dict[int, set[str]] = {}
    for i, modref in enumerate(modrefs):
        found: set[str] = set()

        def callback(argv: list[str]) -> None:
            a = argv + [""] * max(0, 5 - len(argv))
            formodule, dep, is_ext = a[0], a[1], a[4]
            if is_ext != "true":
                found.add(name(dep, formodule))

        try:
            if Walker(builder).walk("for-all-modules-with-meta-ext", callback, modref,
                                    name="build-order-callback") != 0:
                return list(modrefs)
        except Exit:
            return list(modrefs)
        found.discard(names[i])
        deps[i] = found

    #  stable topological sort: the first module (in the given order) whose
    #  dependencies among the remaining modules are all placed
    order: list[int] = []
    remaining = list(range(len(modrefs)))
    while remaining:
        left = {names[j] for j in remaining}
        for i in remaining:
            if not (deps[i] & (left - {names[i]})):
                break
        else:
            #  a cycle between modules of the command line: as given
            order += remaining
            break
        order.append(i)
        remaining.remove(i)
    return [modrefs[i] for i in order]
