"""scbi show: information about modules and the build plan (port of
scbi-show).

Ported: --build-plan[:history][=regex], --module-ref[:version|:variant|
:full], --depends[:direct|:full], --externals[:only], --filter:*,
--no-version, --rdepends, usage; --resolved (scbi.tools.resolved).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from scbi.bashcompat import read_lines_escaped, words
from scbi.planview import display_build_plan
from scbi.plugin import formats

USAGE = """
SCBI-SHOW {version}

{argv0} show [options] plug-in1 [plug-in2...]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --plugins=<dir>    specify the plugins' directory
   -e | --env=<name>       environment file ~/.scbi-<name>
      | --depends:n        list module's dependencies (direct, full)
   -r | --rdepends         list module's reverse dependencies
      | --externals:n      list module's external dependencies
      | --no-version       do not display modules/externals version
      | --filter:n         filter depends/external for dev or runtime
      | --build-plan:n     list current plan
      | --module-ref:n     display variant/version of specific module
      | --resolved         display the plug-in resolved for the module
      | --stat             display some status of current setup"""


def main(driver, args: list[str]) -> int | None:
    #  getopt -u ... -- $* (unquoted) then set -- $ALLOPTS
    proc = subprocess.run(
        ["getopt", "-u", "-o", "kld",
         "-l", "depends:direct,depends:full,depends,rdepends,build-plan::",
         "-l", "build-plan:history::,externals,externals:only,no-version",
         "-l", "filter:all,filter:dev,filter:runtime,module-ref",
         "-l", "module-ref:version,module-ref:variant,module-ref:full,resolved",
         "--", *words(" ".join(args))],
        capture_output=True, text=True, env=driver.base_env())
    if proc.returncode != 0:
        sys.stdout.write(proc.stderr)
        print('try "scbi show --help" for more information.')
        return 1
    opts = words(proc.stdout)

    do_deps, do_ext, do_rdeps, list_ver, filt = driver.get("DO_DEPS") or "no", "no", "true", "yes", "all"
    do_plan, plan_filter, do_mod_ver, do_resolved = "no", "", "no", False
    i = 0
    while i < len(opts):
        a = opts[i]
        nxt = opts[i + 1] if i + 1 < len(opts) else ""
        if a == "--depends:direct":
            do_deps = "yes-direct"
        elif a in ("--depends:full", "--depends"):
            do_deps = "yes"
        elif a == "--rdepends":
            do_rdeps = "yes"
        elif a == "--externals:only":
            do_ext = "yes-only"
        elif a == "--externals":
            do_ext = "yes"
        elif a == "--no-version":
            list_ver = "no"
        elif a in ("--filter:all", "--filter:dev", "--filter:runtime"):
            filt = a.split(":", 1)[1]
        elif a in ("--build-plan:history", "--build-plan"):
            do_plan = "history" if a.endswith("history") else "yes"
            if nxt != "--":
                plan_filter = nxt
        elif a == "--resolved":
            do_resolved = True
        elif a in ("--module-ref", "--module-ref:version", "--module-ref:variant", "--module-ref:full"):
            do_mod_ver = {"--module-ref": "full", "--module-ref:version": "ver",
                          "--module-ref:variant": "var", "--module-ref:full": "full"}[a]
            i += 1
        i += 1

    if driver.get("DO_HELP") == "yes":
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0

    if do_ext != "no" and do_deps == "no":
        do_deps = "yes"

    if do_deps != "no":
        driver.set("DO_DEPS", do_deps)
        driver.set("DO_QUIET", "yes")
        return show_depends(driver, do_deps, do_ext, list_ver, filt)

    if do_rdeps == "yes":
        return show_rdepends(driver)

    if do_resolved:
        from scbi.tools import resolved

        return resolved.show(driver, words(" ".join(driver.modules)))

    plan = driver.plan
    if do_mod_ver != "no":
        modules = words(" ".join(driver.modules))
        out = []
        for n, module in enumerate(modules):
            info = (plan.module_ref(module) + [""] * 4)[:4]
            _, variant, kind, ref = info
            if kind == "VERSION":
                ref = f"#{ref}"
            if do_mod_ver == "ver":
                text = ref
            elif do_mod_ver == "var":
                text = variant
            else:
                if ref == "NONE":
                    ref = ""
                text = (f"/{variant}" if variant else "") + (f":{ref}" if ref else "")
            #  echo -n $x (unquoted)
            out.append(" ".join(words(text)))
            if len(modules) > 1 and module != modules[-1]:
                out.append("\n")
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        return 0

    if do_plan != "no":
        regex = f"({plan_filter.replace(',', '|')})" if plan_filter else ""
        for line in display_build_plan(plan, do_plan if do_plan == "history" else "yes", regex):
            print(line)
        return 0

    print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
    return 0


def show_depends(driver, do_deps: str, do_ext: str, list_ver: str, filt: str) -> int:
    """--depends / --externals: for-all-modules-with-meta-ext with
    shw-register-depends-callback, then ``sort | uniq``."""
    from scbi.build import Builder
    from scbi.walker import Walker, get_pkg_version

    plan = driver.plan
    found: list[str] = []

    def callback(argv: list[str]) -> None:
        a = argv + [""] * max(0, 6 - len(argv))
        formodule, modref, level, depends_kind, is_ext = a[:5]
        is_build = "true" if depends_kind == "build" else "false"
        selext = do_ext != "no" or is_ext == "false"
        selbuild = "true" if filt in ("all", "dev") else "false"
        selected = selbuild == is_build or filt == "all"
        if do_deps == "yes-direct" and level != "1":
            selected = False
        if do_ext == "yes-only" and is_ext == "false":
            selected = False
        if not (selext and selected):
            return
        #  SCBI_FILTER is never "run" (the get-lib-for-dev case is dead code)
        mod = modref
        if list_ver == "yes":
            info = (plan.module_ref(modref, formodule) + [""] * 4)[:4]
            module, ref = info[0], info[3]
            if ref == "NONE":
                if is_ext == "true":
                    v = get_pkg_version(driver, module)
                    mod = f"{module}:{v}" if v else module
                else:
                    mod = module
            else:
                mod = f"{module}:{ref}"
            if builder.is_host_dep(modref):
                #  the build for the host in a cross build
                mod = f"host@{mod}"
        found.extend(words(mod))

    builder = Builder(driver)
    walker = Walker(builder)
    res = 0
    for module in words(" ".join(driver.modules)):
        res = walker.walk("for-all-modules-with-meta-ext", callback, module,
                          name="shw-register-depends-callback")
    if res != 0:
        return 1
    _sort_uniq(driver, found)
    return 0


def _sort_uniq(driver, items: list[str]) -> None:
    if items:
        #  sort | uniq (the locale order of sort)
        env = driver.base_env()
        out = subprocess.run(["sort"], input="".join(f"{m}\n" for m in items), capture_output=True,
                             text=True, env=env).stdout
        sys.stdout.write(subprocess.run(["uniq"], input=out, capture_output=True, text=True, env=env).stdout)
        sys.stdout.flush()


#  [[:space:]] of the Bash regexps
_SP = r"[ \t\n\r\f\v]"


def name_with_variants(plg: str, m: str, for_: str) -> str:
    """Port of ``get-name-with-variants``."""
    tag = ""
    if re.search(f"-cross{_SP}*$", m):
        tag += "cross"
        m = m[:-6] if m.endswith("-cross") else m
    if m.startswith(plg):
        m = m[len(plg):]
    if m.startswith("-"):
        m = m[1:]
    v = m.replace("-", ".").replace(".common", "").replace("common.", "").replace("common", "")
    if v:
        if tag:
            tag += "/"
        tag += v
    if tag:
        tag = f" [{tag}]"
    if for_:
        for_ = f" ({for_})"
    return f"{plg}{tag}{for_}"


_DEPS_HOOK = re.compile(r"((pre|post)-)?(cross-)?(modules|depends)\(\)")


def deps_hooks(module: str, plugin: Path, found: list[str]) -> None:
    """Port of ``get-deps-hooks``: the hooks of a plug-in echoing
    ``module``."""
    pgname = plugin.name
    try:
        echo = re.compile(f"echo{_SP}*{module}{_SP}*$")
    except re.error:
        return
    check, current = False, ""
    try:
        text = plugin.read_text(errors="surrogateescape")
    except OSError:
        return
    for line in read_lines_escaped(text):
        if check:
            if echo.search(line):
                found.append(current)
            elif "}" in line:
                check = False
        if not check and _DEPS_HOOK.search(line):
            v = line[len("function "):] if line.startswith("function ") else line
            v = v[:-2] if v.endswith("()") else v
            if "modules" in line:
                v = v[:-len("-modules")] if v.endswith("-modules") else v
                current = name_with_variants(pgname, v, "modules")
            elif "build-depends" in line:
                v = v[:-len("-build-depends")] if v.endswith("-build-depends") else v
                current = name_with_variants(pgname, v, "build")
            elif "test-depends" in line:
                v = v[:-len("-test-depends")] if v.endswith("-test-depends") else v
                current = name_with_variants(pgname, v, "test")
            else:
                v = v[:-len("-depends")] if v.endswith("-depends") else v
                current = name_with_variants(pgname, v, "")
            check = True


#  hook -> label of the dependency kind (as get-deps-hooks)
_DEPENDS_FOR = {"depends": "", "build-depends": "build", "tests-depends": "test", "modules": "modules"}


def definition_depends_hooks(module: str, path: Path, found: list[str]) -> None:
    """The hooks of a plug-in definition (any format) listing ``module`` (in
    a value, guarded or not), named as get-deps-hooks names those of a Bash
    plug-in."""
    from scbi.modref import strip_host
    from scbi.plugin import formats
    from scbi.plugin.model import PLAIN, Guarded, Values

    try:
        pdef = formats.load(path)
    except (formats.PluginFormatError, OSError):
        return

    def values(items) -> list[str]:
        out: list[str] = []
        for it in items:
            if isinstance(it, Guarded):
                out += values(it.items)
            elif isinstance(it, str):
                out.append(it)
        return out

    plg = pdef.name
    for key, body in pdef.hooks.items():
        if key.hook not in _DEPENDS_FOR or not isinstance(body, Values):
            continue
        #  host@<module>: the module too (its build for the host)
        if module not in [strip_host(v.strip()) for v in values(body.items)]:
            continue
        tag = "cross" if key.cross else ""
        if key.qualifier not in (PLAIN, "common"):
            tag += ("/" if tag else "") + key.qualifier
        for_ = _DEPENDS_FOR[key.hook]
        found.append(plg + (f" [{tag}]" if tag else "") + (f" ({for_})" if for_ else ""))


def show_rdepends(driver) -> int:
    """--rdepends: port of ``get-rdepends`` for each module, then
    ``sort | uniq``. The plug-ins are the files whose text has a line
    ``echo <module>`` (grep -sE "echo *<module> *$" $SCBI_PLUGINS/*)."""
    plugins = Path(driver.get("SCBI_PLUGINS"))
    found: list[str] = []
    for modref in words(" ".join(driver.modules)):
        module = (driver.plan.module_ref(modref) + [""])[0]
        try:
            grep = re.compile(f"echo *{module} *$")
        except re.error:
            continue
        try:
            files = sorted(f for f in os.listdir(plugins) if not f.startswith("."))
        except OSError:
            files = []
        for name in files:
            path = plugins / name
            if not path.is_file():
                continue
            if formats.format_of(name) is not None:
                definition_depends_hooks(module, path, found)
                continue
            if formats.find(plugins, name) is not None:
                #  the definition file is the one in use
                continue
            try:
                lines = path.read_text(errors="surrogateescape").splitlines()
            except OSError:
                continue
            for line in lines:
                if grep.search(line):
                    deps_hooks(module, path, found)
    _sort_uniq(driver, found)
    return 0
