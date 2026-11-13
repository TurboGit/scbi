"""The command hooks converted to the command language (plugin/liftcmd.py)
run by the interpreter (hooks/cmdlang.py) compared with the Bash
functions, on every plug-in of scripts.d and tests/scripts.d, native and
cross: same commands executed (the build tools are replaced by a
recorder), same output, status and files.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from corpus import plugin_files
from oracle import REPO_ROOT, BashOracle
from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.cmdlang import Runner, State, parse
from scbi.hooks.context import HookContext
from scbi.plugin import catalog
from scbi.plugin.lift import body_lines, parse_hook_name, split_params
from scbi.plugin.liftcmd import CmdUnliftable, lift_commands
from scbi.plugin.registry import Registry
from scbi.vercmp import VERSION_ERROR, VERSION_OK
from known_diffs import converted_hook_differs

HOST = "x86_64-linux-gnu"
#  driver associative array used by some hooks (${SCBI_MODULES_DIR[m]})
MODULES_DIR = {"c-gprconfig-kb@src": "/kb/src", "lib1": "/lib1"}
CROSS = "arm-linux-gnueabi"
#  real tools (file handling), everything else is recorded
REAL = ("mkdir cp rm ln mv touch cat ls head tail grep sed wc tr sort cut basename dirname printf "
        "env test find chmod realpath readlink true false pwd awk tee uniq xargs").split()
RECORDER = """#!/bin/sh
echo "$(basename "$0") $*" >> "$REC"
echo "REC $(basename "$0") $*"
"""


def hooks_of(directory: Path):
    """(plugin, function, key or None, body lines, params mapping) of the
    command hooks and functions which convert."""
    reg = Registry(directory, read_formats=False)
    result = []
    plugins = [p for p in plugin_files() if Path(p).parent == directory]
    for p in plugins:
        try:
            reg.load_module(Path(p).name)
        except Exception:  # noqa: BLE001
            continue
    for p in plugins:
        plugin = Path(p).name
        trace = reg.traces.get(plugin)
        if trace is None:
            continue
        for name, definition in trace.functions.items():
            key = parse_hook_name(plugin, name)
            if key is not None and catalog.spec(key.hook).kind != catalog.COMMAND:
                continue
            params, rest = split_params(body_lines(definition))
            pmap = ({i + 1: q for i, q in enumerate(catalog.spec(key.hook).params)} if key
                    else {n: q for q, n in params})
            try:
                text = lift_commands(rest, pmap)
            except CmdUnliftable:
                continue
            result.append((plugin, name, key, text, pmap))
    return reg, result


def make_bin(root: Path, names: set[str]) -> Path:
    bindir = root / "bin"
    bindir.mkdir(parents=True)
    for t in REAL:
        path = shutil.which(t)
        if path:
            (bindir / t).symlink_to(path)
    rec = bindir / ".recorder"
    rec.write_text(RECORDER)
    rec.chmod(0o755)
    for n in names:
        if n and "/" not in n and not (bindir / n).exists() and re.fullmatch(r"[\w.+-]+", n):
            (bindir / n).symlink_to(rec)
    return bindir


def command_names(text: str) -> set[str]:
    names = set()
    for line in text.split("\n"):
        for part in re.split(r"&&|\|\||\|", line):
            words = part.strip().split()
            while words and re.match(r"^\w+=", words[0]):
                words.pop(0)
            if words and words[0] not in ("if", "elif", "else:", "for", "write", "append"):
                names.add(words[0])
            m = re.search(r"\b= (?:output|output-words) (\S+)", line)
            if m:
                names.add(m.group(1))
    return names


_LOC = re.compile(r"(?m)^[^\n]*?: line \d+: ")


def normalize(text: str, root: Path) -> str:
    text = text.replace(str(root), "<root>")
    text = _LOC.sub("<loc>: ", text)
    #  "No such file or directory" (Bash, a path) / "command not found"
    text = re.sub(r"<loc>: (\S+): (?:No such file or directory|command not found)",
                  r"<loc>: \1: not found", text)
    return text


def tree(root: Path, mask: Path) -> list[str]:
    out = []
    for dirpath, dirs, files in os.walk(root):
        for f in sorted(files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]):
            p = Path(dirpath, f)
            rel = str(p.relative_to(root))
            if p.is_symlink():
                out.append(f"{rel} -> {os.readlink(p)}".replace(str(mask), "<root>"))
            else:
                #  here-documents: the common indentation is not kept
                lines = [ln.strip() for ln in p.read_text(errors="replace").splitlines()]
                out.append(f"{rel} {lines}".replace(str(mask), "<root>"))
    return sorted(out)


def run_case(tmp: Path, reg, oracle, plugin, name, key, text, target, plugins_dir, pmap):
    #  a variant hook runs when the module is built with that variant
    variant = key.qualifier if key and key.qualifier not in ("", "common", "default") else "default"
    params = {"PREFIX": "", "TARGET": target, "VARIANT": variant, "OPTIONS": "", "KIND": "", "REF": ""}
    names = command_names(text) | {"gprbuild", "make", "cmake"}
    #  the SCBI_* variables of the Bash prelude, given to both sides
    dump = oracle.run('for v in $(compgen -v SCBI_); do [[ ${!v@a} == *[aA]* ]] || '
                      'printf "%s=%s\\0" "$v" "${!v}"; done', check=False).stdout
    prelude = dict(item.split("=", 1) for item in dump.split("\0") if "=" in item)
    results = {}
    for side in ("bash", "py"):
        work = tmp / side / "w"
        work.mkdir(parents=True)
        bindir = make_bin(tmp / side, names)
        prefix = str(tmp / side / "prefix")
        env = {"PATH": str(bindir), "HOME": str(tmp / side), "REC": str(tmp / side / "rec"),
               "SCBI_JOBS": "2", "SCBI_HALF_JOBS": "1", "SCBI_HOST": HOST, "SCBI_TARGET": target,
               "SCBI_BDIR": str(tmp / side / "bdir"), "VERSION_OK": VERSION_OK, "VERSION_ERROR": VERSION_ERROR,
               "LANG": "C", "LC_ALL": "C"}
        env = {**prelude, **env}
        p = dict(params, PREFIX=prefix)
        args = [p[q] for q in (catalog.spec(key.hook).params if key else ())]
        if side == "bash":
            script = (f"source {plugins_dir}/{plugin} > /dev/null 2>&1\n"
                      + "".join(f"export {k}={v!r}\n" for k, v in env.items() if k not in prelude
                                or prelude[k] != v)
                      #  the driver state: the module is loaded (get-caller), the
                      #  hook parameters visible by dynamic scope (hooks
                      #  without "local VARIANT=$3"...)
                      + f"declare -A SCBI_MODVER 2>/dev/null; SCBI_MODVER[{plugin}]={plugin}"
                      + (f"/{variant}\n" if variant != "default" else "\n")
                      + (f"PREFIX={prefix!r} TARGET={target!r} VARIANT={variant}\n" if key else "")
                      + "declare -A SCBI_MODULES_DIR=("
                      + " ".join(f"[{k!r}]={v!r}" for k, v in MODULES_DIR.items()) + ")\n"
                      + f"cd {work}\n{name} {' '.join(repr(a) if a else repr('') for a in args)} < /dev/null 2>&1\n"
                      "echo \"STATUS $?\"\n")
            proc = oracle.run(script, {"HOME": env["HOME"]}, check=False, timeout=60)
            out = proc.stdout
            status = out.rsplit("STATUS ", 1)[1].strip() if "STATUS " in out else "?"
            out = out.rsplit("STATUS ", 1)[0]
        else:
            #  the config-options of the module, by the Bash hooks
            co = oracle.run(f"source {plugins_dir}/{plugin} > /dev/null 2>&1\n"
                            f"SCBI_TARGET={target}\ncd {work}\n"
                            f"plugin-call-variant-hooks {plugin} config-options {prefix!r} {target} {variant}",
                            {"HOME": env["HOME"]}, check=False).stdout.split("\n")[:-1]
            chunks: list[str] = []
            ctx = HookContext(module=plugin, variant=variant, hook=key.hook if key else "config",
                              #  a function is called without arguments
                              params=dict(p) if key else {q: "" for q in pmap.values()}, env=Environment(ShellVars(dict(env), set(env))),
                              host=HOST, target=target, cwd=work,
                              arrays={"SCBI_MODULES_DIR": dict(MODULES_DIR)})
            funcs = {}
            for fname, (fparams, fbody) in reg_functions(reg, plugin).items():
                funcs[fname] = (fparams, parse(fbody))
            runner = Runner(ctx, f"{plugin}.yaml: {key.hook if key else name}",
                            config_options=lambda: co, functions=funcs)
            #  the global variables of the plug-in (set when it is sourced)
            trace = reg.traces.get(plugin)
            state = State(dict(trace.variables if trace else {}), dict(env), str(work),
                          chunks.append, chunks.append)
            status = str(runner.run(parse(text), state))
            out = "".join(chunks)
        rec = (tmp / side / "rec").read_text() if (tmp / side / "rec").exists() else ""
        results[side] = (status, normalize(out, tmp / side), normalize(rec, tmp / side), tree(tmp / side / "w", tmp / side),
                         tree(tmp / side / "prefix", tmp / side) if (tmp / side / "prefix").exists() else [])
    return results


_FUNCS: dict = {}


def reg_functions(reg, plugin):
    """The plug-in functions (not hooks) converted: name -> (params, text)."""
    if plugin in _FUNCS:
        return _FUNCS[plugin]
    funcs = {}
    trace = reg.traces.get(plugin)
    for name, definition in (trace.functions.items() if trace else []):
        if parse_hook_name(plugin, name) is not None:
            continue
        params, rest = split_params(body_lines(definition))
        try:
            funcs[name] = (tuple(q for q, _ in params), lift_commands(rest, {n: q for q, n in params}))
        except CmdUnliftable:
            pass
    _FUNCS[plugin] = funcs
    return funcs


def unconverted_calls(reg, plugin, text):
    """The functions of the plug-in called by ``text`` which do not convert
    (the interpreter has no definition for them)."""
    trace = reg.traces.get(plugin)
    defined = {n for n in (trace.functions if trace else {}) if parse_hook_name(plugin, n) is None}
    #  hooks of plug-ins inherited with --name (call-post-install): not yet
    #  callable from the interpreter (wired with the steps)
    prefixes = set()
    for call in (trace.calls if trace else []):
        args = call.args
        for i, a in enumerate(args):
            if a.startswith("--name="):
                prefixes.add(a.split("=", 1)[1])
            elif a == "--name" and i + 1 < len(args):
                prefixes.add(args[i + 1])
    inherited = {n for n in command_names(text) if any(n.startswith(x + "-") for x in prefixes)}
    return ((command_names(text) & defined) - set(reg_functions(reg, plugin))) | inherited


CASES = []
for d in (REPO_ROOT / "scripts.d", REPO_ROOT / "tests" / "scripts.d"):
    try:
        _reg, _hooks = hooks_of(d)
    except Exception:  # noqa: BLE001
        continue
    for plugin, name, key, text, _pmap in _hooks:
        if text.strip() in ("", "true"):
            continue
        CASES.append((d, _reg, plugin, name, key, text, _pmap))

#  ORACLE_SHARD=i/n runs one slice of the cases (parallel runs by hand)
if os.environ.get("ORACLE_SHARD"):
    _i, _n = map(int, os.environ["ORACLE_SHARD"].split("/"))
    CASES = CASES[_i::_n]


@pytest.mark.oracle
@pytest.mark.parametrize("target", [HOST, CROSS], ids=["native", "cross"])
@pytest.mark.parametrize("case", CASES, ids=[c[3] for c in CASES])
def test_converted_command_hook_same_as_bash(tmp_path, case, target):
    directory, reg, plugin, name, key, text, pmap = case
    if converted_hook_differs(name, text):
        pytest.skip("Bash hook broken, fixed by the conversion (known_diffs)")
    missing = unconverted_calls(reg, plugin, text)
    if missing:
        pytest.skip(f"calls plug-in functions which do not convert: {' '.join(sorted(missing))}")
    oracle = BashOracle(tmp_path / "oracle", plugins_dir=directory)
    res = run_case(tmp_path, reg, oracle, plugin, name, key, text, target, directory, pmap)
    assert res["py"] == res["bash"], text
