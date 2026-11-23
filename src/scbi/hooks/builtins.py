"""Built-in functions usable in the values and environment actions of plug-in definitions.

Ports of the runtime helpers of scripts.d/0_runtime callable as ``$(...)``:
get-version, get-build-type, is-enabled, last-modified-directory,
get-os-inc-dir, and of the commands basename and ls. Each returns the
standard output of the Bash version (without the trailing newline, as a
command substitution would). Also the string functions uppercase and
lowercase; ``$(if <condition> then A [else B])`` is evaluated by
scbi.hooks.expand.

Arguments are given after expansion (including pathname expansion of
unquoted globs, done by the caller as Bash does when calling a function).
"""

from __future__ import annotations

import glob as _glob
import os
import re
import shutil
import subprocess
from pathlib import Path

from scbi.bashcompat import GLOB_CHARS, words
from scbi.hooks.context import HookContext


class BuiltinError(Exception):
    pass


# ------------------------------------------------------------ globbing


def bash_glob(pattern: str, cwd: Path) -> list[str]:
    """Pathname expansion of one word (no match: the word itself)."""
    if not GLOB_CHARS & set(pattern):
        return [pattern]
    matches = _glob.glob(pattern, root_dir=None if os.path.isabs(pattern) else cwd)
    return sorted(matches) if matches else [pattern]


def echo_expand(text: str, cwd: Path) -> str:
    """``echo $text``: word splitting and pathname expansion."""
    return " ".join(m for w in words(text) for m in bash_glob(w, cwd))


def _exists(path: str, cwd: Path) -> bool:
    return os.path.lexists(path if os.path.isabs(path) else cwd / path)


# ------------------------------------------------------------ helpers


def get_version(ctx: HookContext) -> str:
    """Port of ``get-version``: version of the caller plug-in in the plan,
    as seen by the module using it."""
    #  An env hook is called by the module using it (last in the modules
    #  list), the other hooks while handling the module itself.
    idx = -1 if re.search(r"env$", ctx.hook) else -2
    for_module = ""
    if len(ctx.modules_list) >= -idx:
        for_module = ctx.modules_list[idx]
    info = ctx.plan.module_ref(ctx.module, for_module or "@root")
    return info[3] if len(info) > 3 else ""


def get_module_version(ctx: HookContext, modref: str) -> str:
    """Port of ``get-module-version MODREF``."""
    info = ctx.plan.module_ref(modref, ctx.module)
    return info[3] if len(info) > 3 else ""


def get_build_type(ctx: HookContext, kind: str = "", default: str = "") -> str:
    """Port of ``get-build-type KIND DEFAULT``."""
    generic = ctx.env.get(f"SCBI_{kind}_BUILD_TYPE")
    module = ctx.env.get(f"SCBI_{ctx.module.replace('-', '_')}_BUILD_TYPE")
    if generic:
        default = generic
    if module:
        default = module
    return default


def is_enabled(ctx: HookContext, feature: str, then: str = "", other: str = "") -> tuple[bool, str]:
    """Port of ``is-enabled FEATURE [THEN] [ELSE]``: (status, output)."""
    feat = feature.replace("-", "_", 1)
    value = ctx.env.get(f"SCBI_{feat}_SET")
    if not value:
        generic = ctx.env.get(f"SCBI_{feat}_FEATURE")
        module = ctx.env.get(f"SCBI_{ctx.module.replace('-', '_')}_{feat}_FEATURE")
        value = module or generic
    if value == "true":
        return True, then or "yes"
    return False, other


def last_modified_directory(ctx: HookContext, pattern: str = "") -> str:
    """Port of ``last-modified-directory PATTERN`` (``ls -td $PATTERN | head -1``)."""
    paths = [m for w in words(pattern) for m in bash_glob(w, ctx.cwd)]
    existing = [p for p in paths if _exists(p, ctx.cwd)]
    if not existing:
        return ""

    def mtime(p: str) -> int:
        return os.lstat(p if os.path.isabs(p) else ctx.cwd / p).st_mtime_ns

    existing.sort(key=lambda p: (-mtime(p), p))
    return existing[0]


def _ls_ok(pattern: str, cwd: Path) -> bool:
    #  ls $F succeeds when every word (after expansion) exists
    args = [m for w in words(pattern) for m in bash_glob(w, cwd)]
    return bool(args) and all(_exists(a, cwd) for a in args)


def get_os_file(ctx: HookContext, filename: str, *paths: str) -> str:
    """Port of ``get-os-file FILENAME PATH...`` (output of ``echo $FILENAME``)."""
    for p in paths:
        f = f"{p}/{filename}"
        if _ls_ok(f, ctx.cwd):
            filename = f
            break
    return echo_expand(filename, ctx.cwd)


def get_os_inc(ctx: HookContext, f: str) -> str:
    """Port of ``get-os-inc FILE``."""
    t = ctx.target
    bn = f.rsplit("/", 1)[-1]
    r = get_os_file(ctx, f, f"/usr/include/{t}", "/usr/include", f"/usr/include/{t}/*", "/usr/include/*")
    if r != f or bn == f:
        return echo_expand(r, ctx.cwd)
    return get_os_file(ctx, bn, f"/usr/include/{t}", "/usr/include", f"/usr/include/{t}/*", "/usr/include*/*")


def get_os_inc_dir(ctx: HookContext, f: str = "") -> str:
    """Port of ``get-os-inc-dir FILE`` (``echo ${R%/*}``)."""
    r = get_os_inc(ctx, f)
    if "/" in r:
        r = r.rsplit("/", 1)[0]
    return echo_expand(r, ctx.cwd)


_LIB_DIRS = ("/usr/lib*/{t}", "/usr/lib*/{t}/*", "/usr/lib*", "/usr/lib*/*", "/usr/lib*/*/lib*")


def get_os_lib(ctx: HookContext, f: str = "") -> str:
    """Port of ``get-os-lib FILE``: the library in the system directories
    (``serial/libhdf5.so`` or ``libGL.so``), else FILE."""
    dirs = [d.format(t=ctx.target) for d in _LIB_DIRS]
    bn = f.rsplit("/", 1)[-1]
    r = get_os_file(ctx, f, *dirs)
    if r != f or bn == f:
        return r
    return get_os_file(ctx, bn, *dirs)


def get_os_lib_dir(ctx: HookContext, f: str = "") -> str:
    """Port of ``get-os-lib-dir FILE``: the directory of get-os-lib."""
    r = get_os_lib(ctx, f)
    return r.rsplit("/", 1)[0] if "/" in r else r


def get_os_bin(ctx: HookContext, f: str = "") -> str:
    """Port of ``get-os-bin FILE``: the program in /usr/bin* or
    /usr/lib*/*/bin, else FILE."""
    return get_os_file(ctx, f, "/usr/bin*", "/usr/lib*/*/bin")


def output(ctx: HookContext, *argv: str) -> str:
    """``output COMMAND ARGS...``: the standard output of the command (run
    without shell, in the environment of the hook), without its final
    newlines."""
    if not argv:
        return ""
    try:
        proc = subprocess.run(list(argv), capture_output=True, text=True, cwd=ctx.cwd,
                              env=ctx.env.vars.environ())
    except OSError as e:
        raise BuiltinError(f"output {argv[0]}: {e.strerror}") from None
    return proc.stdout.rstrip("\n")


def get_os_bin_dir(ctx: HookContext, f: str = "") -> str:
    """Port of ``get-os-bin-dir FILE``: the directory of get-os-bin."""
    r = get_os_bin(ctx, f)
    return r.rsplit("/", 1)[0] if "/" in r else r


def dirname(ctx: HookContext, path: str = "") -> str:
    """The dirname command (``.`` when there is no directory)."""
    p = path.rstrip("/")
    if not p:
        return "/" if path else "."
    d = p.rsplit("/", 1)[0] if "/" in p else "."
    return d.rstrip("/") or "/"


def command_path(ctx: HookContext, tool: str = "") -> str:
    """``command -v TOOL``: the path of the tool found in PATH, empty if
    not found."""
    if not tool:
        return ""
    return shutil.which(tool, path=ctx.env.get("PATH") or None) or ""


def store_key(ctx: HookContext, key: str = "") -> str:
    """Port of ``scbi-store-get-key KEY``: the value of KEY in
    ``$SCBI_PLUGINS/.store`` (lines ``KEY VALUE``), empty if not found."""
    store = Path(ctx.env.get("SCBI_PLUGINS") or "") / ".store"
    try:
        lines = store.read_text().splitlines()
    except OSError:
        return ""
    for line in lines:
        k, _, v = line.partition(" ")
        if k == key:
            return v.strip()
    return ""


def module_dir(ctx: HookContext, module: str = "", kind: str = "") -> str:
    """``module-dir MODULE [install|src|build]``: the install (default),
    source or build directory of a module of the build (as
    ``${SCBI_MODULES_DIR[MODULE[@src|@build]]}``), empty when the module
    is not in the build."""
    if kind not in ("", "install", "src", "build"):
        raise BuiltinError(f"module-dir: {kind}: install, src or build expected")
    key = module if kind in ("", "install") else f"{module}@{kind}"
    return ctx.arrays.get("SCBI_MODULES_DIR", {}).get(key, "")


def replace(ctx: HookContext, *args: str) -> str:
    """``replace VALUE CHARS1 [CHARS2]``: each character of CHARS1 in VALUE
    replaced by the character at the same position in CHARS2, removed when
    CHARS2 is empty or not given."""
    if len(args) not in (2, 3):
        raise BuiltinError("replace: a value, the characters to replace and their replacements expected"
                           " (quote a value with blanks)")
    value, chars1, chars2 = (*args, "")[:3]
    if chars2 and len(chars2) != len(chars1):
        raise BuiltinError(f"replace: '{chars1}' and '{chars2}' do not have the same length")
    if not chars2:
        return value.translate({ord(c): None for c in chars1})
    return value.translate({ord(a): b for a, b in zip(chars1, chars2)})


def basename(ctx: HookContext, *args: str) -> str:
    """The basename command (one name, optionally a suffix)."""
    if not args or len(args) > 2:
        raise BuiltinError("basename: one name and an optional suffix expected")
    name = args[0]
    stripped = name.rstrip("/")
    if not stripped:
        return "/" if name else ""
    base = stripped.rsplit("/", 1)[-1]
    if len(args) == 2 and args[1] and base != args[1] and base.endswith(args[1]):
        base = base[: -len(args[1])]
    return base


def ls(ctx: HookContext, *args: str) -> str:
    """The ls command, non-interactive output (one name per line)."""
    def path(a: str) -> Path:
        return Path(a) if os.path.isabs(a) else ctx.cwd / a

    def entries(d: str) -> list[str]:
        return sorted(e for e in os.listdir(path(d)) if not e.startswith("."))

    if not args:
        return "\n".join(entries("."))
    existing = [a for a in args if _exists(a, ctx.cwd)]
    files = sorted(a for a in existing if not path(a).is_dir())
    dirs = sorted(a for a in existing if path(a).is_dir())
    if len(args) == 1 and dirs:
        return "\n".join(entries(dirs[0]))
    blocks = ["\n".join(files)] if files else []
    for d in dirs:
        blocks.append(f"{d}:\n" + "\n".join(entries(d)))
    return "\n\n".join(blocks)


def call(ctx: HookContext, name: str, args: list[str]) -> str:
    """Run built-in ``name`` with ``args``, return its output."""
    if name == "get-version":
        #  get-version [PLUG-IN]: the version of the module, or of a plug-in
        return get_module_version(ctx, args[0]) if args else get_version(ctx)
    if name == "get-build-type":
        return get_build_type(ctx, *args[:2])
    if name == "is-enabled":
        return is_enabled(ctx, *(args + ["", "", ""])[:3])[1]
    if name == "last-modified-directory":
        return last_modified_directory(ctx, *args[:1])
    if name == "get-os-inc-dir":
        return get_os_inc_dir(ctx, *args[:1])
    if name == "get-os-lib":
        return get_os_lib(ctx, *args[:1])
    if name == "get-os-lib-dir":
        return get_os_lib_dir(ctx, *args[:1])
    if name == "get-os-bin":
        return get_os_bin(ctx, *args[:1])
    if name == "output":
        return output(ctx, *args)
    if name == "get-os-bin-dir":
        return get_os_bin_dir(ctx, *args[:1])
    if name == "dirname":
        return dirname(ctx, *args[:1])
    if name == "command-path":
        return command_path(ctx, *args[:1])
    if name == "store-key":
        return store_key(ctx, *args[:1])
    if name == "basename":
        return basename(ctx, *args)
    if name == "ls":
        return ls(ctx, *args)
    if name == "module-dir":
        return module_dir(ctx, *args[:2])
    if name == "replace":
        return replace(ctx, *args)
    if name == "uppercase":
        return " ".join(args).upper()
    if name == "lowercase":
        return " ".join(args).lower()
    raise BuiltinError(f"unknown function {name}")
