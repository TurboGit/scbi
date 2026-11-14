"""User-redefinable runtime functions (define-var...): reference hashes,
guards evaluated in Bash, and hooks run through a redefined define-var."""

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from corpus import plugin_files
from oracle import REPO_ROOT
from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.bashguard import to_bash
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import GuardContext
from scbi.hooks.exec import HookShell, run_env_hook
from scbi.hooks.policy import alternate, is_reference, python_env_allowed, redefined
from scbi.hooks.reference import PORTED, REFERENCE
from scbi.hooks.runtime import load_runtime
from scbi.plan import PlanState
from scbi.plugin import expr, yamlfmt
from scbi.plugin.lift import lift
from scbi.plugin.model import Guarded
from scbi.plugin.registry import Registry

HOST = "x86_64-linux-gnu"
BASE_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C", "LC_ALL": "C"}


def driver_vars(root: Path) -> ShellVars:
    return ShellVars({
        "SCBI_HOST": HOST, "SCBI_TARGET": HOST, "SCBI_IS_WINDOWS": "no",
        "SCBI_ROOT": str(root), "SCBI_PLUGINS": str(REPO_ROOT / "scripts.d"), "HOME": str(root),
    }, {"SCBI_HOST", "SCBI_TARGET", "HOME"})


@pytest.fixture(scope="module")
def runtime(oracle):
    root = Path(oracle.env()["SCBI_ROOT"])
    root.mkdir(exist_ok=True)
    return load_runtime(REPO_ROOT / "scripts.d", driver_vars(root), cwd=root, base_env=BASE_ENV)


# ------------------------------------------------------------ reference


def test_reference_up_to_date(runtime):
    for name, ref in {**REFERENCE, **PORTED}.items():
        current = hashlib.sha256(runtime.functions[name].encode()).hexdigest()
        assert current == ref, f"{name} changed in scripts.d: update its Python port and hooks/reference.py"


def test_redefined(runtime, tmp_path):
    assert redefined(runtime.functions) == []
    assert python_env_allowed(runtime.functions)
    user = {"define-var": "define-var () \n{ \n    echo $*\n}"}
    assert redefined(runtime.functions, user) == ["define-var"]
    assert redefined({}) == list(REFERENCE)
    assert is_reference("get-vcs-data", runtime.functions)
    assert not is_reference("get-vcs-data", runtime.functions, {"get-vcs-data": "get-vcs-data () \n{ \n    echo x\n}"})
    assert redefined(runtime.functions, {"get-vcs-data": "x"}) == []
    #  the Windows runtime has its own define-var
    win = load_runtime(REPO_ROOT / "scripts.d", driver_vars(tmp_path), cwd=tmp_path,
                       base_env=BASE_ENV, os_module="windows")
    #  a known alternate (scbi.env.WINDOWS_DEFINE_VAR), unless cygpath is
    #  a shell function
    assert redefined(win.functions) == []
    assert alternate("define-var", win.functions) == "windows"
    assert alternate("define-var", runtime.functions) is None
    assert python_env_allowed(win.functions)
    assert not python_env_allowed(win.functions, {"cygpath": "cygpath () \n{ \n    echo x\n}"})


@pytest.mark.oracle
def test_windows_define_var_same_as_bash(oracle, monkeypatch):
    from scbi import env as env_mod
    from scbi.env import Environment

    calls = [("SET", "A", "x y"), ("ADD", "L", "a"), ("ADD", "L", "b"), ("ADD", "L", "a"),
             ("APPEND", "L", "c"), ("PREPEND", "L", "c"), ("REMOVE", "L", "b"), ("REMOVE", "M", "z"),
             ("ADD", "PATH", "/"), ("ADD", "PATH", "/no/such/dir"), ("UNSET", "A", "")]
    script = (f"source {REPO_ROOT}/scripts.d/_os_windows\n"
              "function cygpath() { echo \"/cyg$2\"; }\nexport PATH=/usr/bin:/bin\nL=\"\"\n"
              + "\n".join(f'define-var {a} {n} "{v}"' for a, n, v in calls)
              + '\necho "L=$L"\necho "M=${M-unset}"\necho "A=${A-unset}"\necho "PATH=$PATH"')
    expected = oracle.call(script)
    monkeypatch.setattr(env_mod, "WINDOWS_DEFINE_VAR", True)
    monkeypatch.setattr(env_mod, "cygpath", lambda p: "/cyg" + p)
    e = Environment()
    e.export("PATH", "/usr/bin:/bin")
    e.vars.values["L"] = ""
    for a, n, v in calls:
        e.define_var(a, n, v)
    got = "".join(f"{n}={e.vars.values.get(n, 'unset')}\n" for n in ("L", "M", "A", "PATH"))
    assert got == expected


# ----------------------------------------------------- guards in Bash

def corpus_conditions() -> list[str]:
    conds = set()

    def walk(items):
        for it in items:
            if isinstance(it, Guarded):
                conds.add(it.cond)
                walk(it.items)

    for p in plugin_files():
        reg = Registry(p.parent)
        reg.load_module(p.name)
        res = lift(reg.traces[p.name], set(reg.functions))
        for body in res.plugin.hooks.values():
            walk(getattr(body, "items", ()) or getattr(body, "ops", ()))
    return sorted(conds)


CONDITIONS = [
    "ref =~ ^7.8", "ref == 1.2.3", "version(lib2) > 1.9", "version(lib2) <= 1.9",
    "not (version(lib2) =~ 2.0)", "cross", "not cross", "target =~ mingw32",
    "variant == dv", "kind == true", "on deb,12", "on deb or on fed", "on win",
    "build-type(CMAKE,Release) == Debug", "build-type(MAKE,true) == true",
    "enabled(fast)", "not enabled(slow)", "exists(toto)", "exists(present)",
    "(cross or variant == dv) and version(lib2) >= 2.0", "host == x86_64-linux-gnu",
]

CONTEXTS = [
    # (target, variant, kind, ref)
    (HOST, "default", "BRANCH", "7.8.1"),
    ("i686-w64-mingw32", "dv", "true", "1.2.3"),
]

TEMPLATE = r"""
cd "$1"
SCBI_TARGET=$2
SCBI_MODVER=([lib2]="lib2:2.0.1" [gm]="gm/$3:1.2.3")
SCBI_MODULES_LIST=(gm)
SCBI_OS_DISCRIMINANTS=([deb]=yes [12]=yes [linux]=yes)
export SCBI_CMAKE_BUILD_TYPE=Debug SCBI_fast_FEATURE=true
function gm-patches()
{
    local PREFIX=$1 TARGET=$2 VARIANT=$3 KIND=$4 REF=$5
    if eval "$6"; then echo T; else echo F; fi
}
gm-patches /p "$2" "$3" "$4" "$5" "$7"
"""


@pytest.mark.oracle
def test_guards_bash_vs_python(oracle, tmp_path):
    (tmp_path / "present").write_text("")
    conds = sorted(set(CONDITIONS) | set(corpus_conditions()))
    cases = []
    for cond in conds:
        for target, variant, kind, ref in CONTEXTS:
            cases.append((cond, target, variant, kind, ref))
    outputs = oracle.batch(
        TEMPLATE, [(str(tmp_path), t, v, k, r, "", to_bash(c)) for c, t, v, k, r in cases]
    )
    for (cond, target, variant, kind, ref), out in zip(cases, outputs):
        env = Environment(ShellVars({"SCBI_CMAKE_BUILD_TYPE": "Debug", "SCBI_fast_FEATURE": "true"}))
        ctx = HookContext(module="gm", variant=variant, hook="patches", env=env, cwd=tmp_path,
                          params={"PREFIX": "/p", "TARGET": target, "VARIANT": variant, "KIND": kind, "REF": ref},
                          plan=PlanState({"lib2": "lib2:2.0.1", "gm": f"gm/{variant}:1.2.3"}),
                          modules_list=["gm"], host=HOST, target=target,
                          discriminants=frozenset({"deb", "12", "linux"}))
        expected = "T" if expr.evaluate(cond, GuardContext(ctx)) else "F"
        assert out.strip() == expected, (cond, target, variant)


# ------------------------------- define-var redefined, plugin-call-env-hooks

GV_YAML = """
env:
  - add-to-var A x
  - if variant == dv: set-var B y
  - if version(lib2) > 1.9: prepend-to-var C z
  - if variant == other: set-var D never
build-env:
  dv: [set-var E $PREFIX]
"""

M_GV = """
function m-gv-wrapup()
{
    rm -f env.dump

    function define-var()
    {
        local ACTION=$1
        local VAR=$2
        local VALUE=$3

        echo A:$ACTION $VAR = ${VALUE##$PWD} >> env.dump
    }

    plugin-call-env-hooks root gv/dv env
    plugin-call-env-hooks root gv/dv build-env
}
"""


def run_wrapup(runtime, plugins: Path, module: str, deps: list[str], cwd: Path) -> str:
    reg = Registry(plugins)
    for m in [module] + deps:
        assert reg.load_module(m)
    shell = HookShell(runtime, reg.functions, BASE_ENV, loaded=reg.scbi_loaded())
    cwd.mkdir(parents=True, exist_ok=True)
    ctx = HookContext(module=module, variant="default", hook="wrapup", cwd=cwd, host=HOST, target=HOST,
                      modules_list=[module], plan=PlanState({"lib2": "lib2:2.0.1"}),
                      env=Environment(ShellVars({"PATH": BASE_ENV["PATH"]}, {"PATH"})))
    res = shell.run(ctx, f"{module}-wrapup", [str(cwd / "install"), HOST, "default"])
    assert res.returncode == 0, res.output
    return (cwd / "env.dump").read_text()


ORACLE_WRAPUP = r"""
SCBI_PLUGINS="$1"
SCBI_MODVER=([lib2]="lib2:2.0.1")
declare -A SCBI_MODULES_DIR=()
for m in $3; do load-module $m > /dev/null 2>&1; done
mkdir -p "$4" && cd "$4"
"$2-wrapup" "$4/install" x86_64-linux-gnu default > /dev/null 2>&1
cat env.dump
"""


@pytest.mark.oracle
def test_redefined_define_var_legacy_and_yaml(oracle, runtime, tmp_path):
    tests_dir = REPO_ROOT / "tests" / "scripts.d"
    #  test173 plug-ins: legacy lib1
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    for f in ("m-lib1", "lib1"):
        shutil.copy(tests_dir / f, legacy / f)
    #  same with lib1 converted to YAML
    yaml_dir = tmp_path / "yaml"
    yaml_dir.mkdir()
    shutil.copy(tests_dir / "m-lib1", yaml_dir / "m-lib1")
    reg = Registry(tests_dir)
    reg.load_module("lib1")
    res = lift(reg.traces["lib1"], set(reg.functions))
    assert not res.issues
    (yaml_dir / "lib1.yaml").write_text(yamlfmt.dump(res.plugin))

    expected = oracle.batch(ORACLE_WRAPUP, [(str(legacy), "m-lib1", "m-lib1 lib1", str(tmp_path / "bash"))])[0]
    assert "A:ADD C_INCLUDE_PATH = a" in expected
    assert run_wrapup(runtime, legacy, "m-lib1", ["lib1"], tmp_path / "py-legacy") == expected
    assert run_wrapup(runtime, yaml_dir, "m-lib1", ["lib1"], tmp_path / "py-yaml") == expected


def test_redefined_define_var_yaml_guards(runtime, tmp_path):
    d = tmp_path / "plugins"
    d.mkdir()
    (d / "gv.yaml").write_text(GV_YAML)
    (d / "m-gv").write_text(M_GV)
    out = run_wrapup(runtime, d, "m-gv", ["gv"], tmp_path / "work")
    #  guards evaluated with the variant given to plugin-call-env-hooks
    #  (dv) and the plan; ${VALUE##$PWD} strips the work directory
    #  PREFIX given by plugin-call-env-hooks: the install dir of gv/dv
    lines = out.splitlines()
    assert lines[:3] == ["A:ADD A = x", "A:SET B = y", "A:PREPEND C = z"]
    assert lines[3].startswith("A:SET E = ") and lines[3].endswith("/builds/gv/x86_64-linux-gnu-dv/install")
    assert len(lines) == 4


def test_global_redefinition_uses_bash(runtime, tmp_path):
    d = tmp_path / "plugins"
    d.mkdir()
    (d / "gv.yaml").write_text(GV_YAML)
    reg = Registry(d)
    reg.load_module("gv")
    #  an environment file redefining define-var for the whole run
    user = {"define-var": f"define-var () \n{{ \n    echo \"$1 $2=$3\" >> {tmp_path}/captured\n}}"}
    assert not python_env_allowed(runtime.functions, user)
    shell = HookShell(runtime, reg.functions, BASE_ENV, loaded=reg.scbi_loaded())
    ctx = HookContext(module="gv", variant="dv", hook="env", cwd=tmp_path, host=HOST, target=HOST,
                      modules_list=["gv"], plan=PlanState({"lib2": "lib2:2.0.1"}),
                      env=Environment(ShellVars({"PATH": BASE_ENV["PATH"]}, {"PATH"}, dict(user))))
    run_env_hook(shell, ctx, "gv-env", ["/p", HOST, "dv"], python_env=False)
    assert (tmp_path / "captured").read_text().splitlines() == ["ADD A=x", "SET B=y", "PREPEND C=z"]
    #  with the reference define-var the Python evaluation is used
    ctx2 = HookContext(module="gv", variant="dv", hook="env", cwd=tmp_path, host=HOST, target=HOST,
                       modules_list=["gv"], plan=PlanState({"lib2": "lib2:2.0.1"}))
    run_env_hook(shell, ctx2, "gv-env", ["/p", HOST, "dv"], python_env=True)
    assert ctx2.env.get("A") == "x" and ctx2.env.get("B") == "y" and ctx2.env.get("C") == "z"
