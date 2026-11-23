"""Evaluation of YAML values and environment actions (scbi.hooks) compared
with the execution of the original Bash hooks by the Bash runtime."""

import os
import time
from functools import cache
from pathlib import Path

import pytest

from corpus import plugin_files
from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks import builtins
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import apply_env, eval_values, set_plugin_vars
from scbi.hooks.expand import ExpandError, check, expand
from scbi.plan import PlanState
from scbi.plugin import catalog
from scbi.plugin.lift import lift
from scbi.plugin.model import EnvOp, EnvOps, Guarded, Values
from scbi.plugin.registry import Registry

HOST = "x86_64-linux-gnu"


def ctx(tmp_path, **kw) -> HookContext:
    c = HookContext(module="m", variant="default", hook="env", cwd=tmp_path, host=HOST, target=HOST)
    for k, v in kw.items():
        setattr(c, k, v)
    return c


# ---------------------------------------------------------------- unit


def test_expand_variables_and_operators(tmp_path):
    c = ctx(tmp_path, params={"PREFIX": "/opt/x"}, env=Environment(ShellVars({"P": "/a/include/b"})))
    c.arrays = {"SCBI_MODULES_DIR": {"lib@build": "/b/lib"}}
    assert expand("$PREFIX/lib:${PREFIX}x:$NOPE.", c) == "/opt/x/lib:/opt/xx:."
    assert expand("${P%%/include*}|${P%/*}|${P#*/}|${P##*/}", c) == "/a|/a/include|a/include/b|b"
    assert expand("${SCBI_MODULES_DIR[lib@build]}/x", c) == "/b/lib/x"
    c.arrays = {"SCBI_MODULES_DIR": {"lib": "/i/lib", "lib@src": "/s/lib", "lib@build": "/b/lib"}}
    assert expand("$(module-dir lib)|$(module-dir lib install)|$(module-dir lib src)|$(module-dir lib build)",
                  c) == "/i/lib|/i/lib|/s/lib|/b/lib"
    assert expand("[$(module-dir nope)]", c) == "[]"
    with pytest.raises(ExpandError, match="install, src or build expected"):
        expand("$(module-dir lib bad)", c)
    assert expand("cost $", c) == "cost $"


def test_expand_builtins(tmp_path):
    for d in ("python3.9", "python3.11"):
        (tmp_path / "lib" / d).mkdir(parents=True)
    old = time.time() - 100
    os.utime(tmp_path / "lib" / "python3.9", (old, old))
    c = ctx(tmp_path, params={"PREFIX": str(tmp_path)})
    #  the unquoted glob is expanded before the call: first match only
    assert expand("$(last-modified-directory $PREFIX/lib/python*)", c) == f"{tmp_path}/lib/python3.11"
    assert expand('$(last-modified-directory "$PREFIX/lib/python*")', c) == f"{tmp_path}/lib/python3.11"
    assert expand("$(basename $PREFIX/lib/python3.9)", c) == "python3.9"
    assert expand("$(ls $PREFIX/lib)", c) == "python3.11 python3.9"
    #  default value
    assert expand("${NOPE:-dflt}/${PREFIX:-x}", c) == f"dflt/{tmp_path}"


@pytest.mark.parametrize(
    "text", ["$(cat x)", "${X:=a}", "$1", "$(ls", "${A[b]c}"]
)
def test_expand_check_rejects(text):
    with pytest.raises(ExpandError):
        check(text)


def test_get_build_type_and_is_enabled(tmp_path):
    e = Environment(ShellVars({"SCBI_CMAKE_BUILD_TYPE": "Debug", "SCBI_c_x_BUILD_TYPE": "Rel",
                               "SCBI_fast_FEATURE": "true", "SCBI_c_x_slow_FEATURE": "true"}))
    c = ctx(tmp_path, module="c-y", env=e)
    assert builtins.get_build_type(c, "CMAKE", "Release") == "Debug"
    assert builtins.get_build_type(c, "MAKE", "true") == "true"
    c.module = "c-x"
    assert builtins.get_build_type(c, "CMAKE", "Release") == "Rel"
    assert builtins.is_enabled(c, "fast") == (True, "yes")
    assert builtins.is_enabled(c, "slow", "on", "off") == (True, "on")
    c.module = "c-y"
    assert builtins.is_enabled(c, "slow", "on", "off") == (False, "off")


def test_get_version(tmp_path):
    plan = PlanState({"m": "m:1.2", "app=m": "m:2.0"})
    c = ctx(tmp_path, plan=plan, modules_list=["app", "m"], hook="config")
    assert builtins.get_version(c) == "2.0"  # handled for app
    c.hook = "env"
    assert builtins.get_version(c) == "1.2"  # env called by m itself (last)
    c.modules_list = ["m"]
    c.hook = "config"
    assert builtins.get_version(c) == "1.2"


def test_values_and_env_actions(tmp_path):
    from scbi.plugin.model import EnvOp, Guarded

    c = ctx(tmp_path, params={"PREFIX": "/p", "REF": "7.8.1"},
            plan=PlanState({"lib2": "lib2:2.0.1"}), env=Environment(ShellVars({"A": "x"}, {"A"})))
    vals = Values(("a", Guarded("ref =~ ^7.8", ("fix.diff",)), Guarded("version(lib2) < 1.9", ("old",))))
    assert eval_values(vals, c) == ["a", "fix.diff"]
    apply_env(EnvOps((
        EnvOp("local", ("L", "$PREFIX/lib")),
        EnvOp("add-to-var", ("A", "$L")),
        EnvOp("export", ("B", "${L%/lib}")),
        EnvOp("mkdir", ("out/dir",)),
        Guarded("cross", (EnvOp("set-var", ("C", "1")),)),
    )), c)
    assert c.env.get("A") == "/p/lib:x" and c.env.get("B") == "/p" and "C" not in c.env.vars.values
    assert (tmp_path / "out" / "dir").is_dir()


def test_string_functions_and_if(tmp_path):
    e = Environment(ShellVars({"SCBI_CMAKE_BUILD_TYPE": "Debug"}))
    c = ctx(tmp_path, params={"VARIANT": "mpi"}, env=e)
    assert expand("$(uppercase $VARIANT)-$(lowercase ABC Def)", c) == "MPI-abc def"
    assert expand("-DA=$(if build-type(CMAKE,Release) == Debug then ON else OFF)", c) == "-DA=ON"
    assert expand("-DA=$(if build-type(CMAKE,Release) != Debug then ON else OFF)", c) == "-DA=OFF"
    #  else is optional, the values are words (quotes removed, expanded)
    assert expand("[$(if variant == other then x)]", c) == "[]"
    assert expand('$(if $VARIANT == mpi then "a  b" $VARIANT else c)', c) == "a  b mpi"
    #  conditions with parentheses, and/or; nested functions
    assert expand("$(if (variant == mpi and cross) or variant == x then 1 else $(uppercase no))", c) == "NO"
    #  then/else inside quotes are not keywords
    assert expand('$(if variant == mpi then "if then else")', c) == "if then else"


@pytest.mark.parametrize("text", ["$(if variant == x)", "$(if then a)", "$(if variant == then a else b else c)",
                                  "$(if variant === x then a)"])
def test_if_syntax_errors(text):
    with pytest.raises(ExpandError):
        check(text)


def test_local_assign_in_values_and_env(tmp_path):
    from scbi.plugin import construct
    from scbi.plugin.model import LocalAssign

    e = Environment(ShellVars({"SCBI_CMAKE_BUILD_TYPE": "Debug"}))
    c = ctx(tmp_path, params={"PREFIX": "/p"}, env=e)
    items = [construct.value(t) for t in (
        "BT = get-build-type CMAKE Release",
        "-DLLVM_ENABLE_ASSERTIONS=$(if $BT == Debug then ON else OFF)",
        "N = $PREFIX/lib",
        "-L$N",
        "E =",
        "[$E]",
    )]
    assert items[0] == LocalAssign("BT", "get-build-type CMAKE Release")
    assert items[0].text == "$(get-build-type CMAKE Release)" and items[2].text == "$PREFIX/lib"
    assert eval_values(Values(tuple(items)), c) == ["-DLLVM_ENABLE_ASSERTIONS=ON", "-L/p/lib", "[]"]
    #  a guard can use the variable
    c = ctx(tmp_path, env=e)
    from scbi.plugin.model import Guarded
    vals = Values((construct.value("BT = get-build-type CMAKE Release"), Guarded("$BT == Debug", ("dbg",))))
    assert eval_values(vals, c) == ["dbg"]
    #  environment list
    c = ctx(tmp_path, env=Environment(ShellVars({}, set())), params={"VARIANT": "mpi"})
    apply_env(EnvOps((construct.env_action("U = uppercase $VARIANT"),
                      construct.env_action("set-var LIBNAME lib$U"))), c)
    assert c.env.get("LIBNAME") == "libMPI" and "U" not in c.env.vars.values
    #  an unknown function is refused when the plug-in is loaded
    with pytest.raises(construct.DefinitionError):
        construct.value("X = $(cat file)")


def test_import(tmp_path):
    c = ctx(tmp_path, env=Environment(ShellVars({"PATH": os.environ["PATH"]}, {"PATH"})))
    apply_env(EnvOps((__import__("scbi.plugin.model").plugin.model.EnvOp(
        "import", ("echo 'export IMPORTED=yes; OTHER=1'",)),)), c, base_env={"PATH": os.environ["PATH"]})
    assert c.env.get("IMPORTED") == "yes" and "IMPORTED" in c.env.vars.exported
    assert c.env.get("OTHER") == "1"


def test_import_opam_like(tmp_path):
    from scbi.plugin.model import EnvOp

    script = tmp_path / "fake-opam"
    script.write_text("#!/bin/sh\nprintf \"%s\\n\" \"OPAM_SWITCH_PREFIX='/o p/default'; export OPAM_SWITCH_PREFIX;\" "
                      "\"PATH='/o/bin:$PATH'; export PATH;\" \"unset GONE;\"\n")
    script.chmod(0o755)
    env = Environment(ShellVars({"PATH": "/usr/bin:/bin", "GONE": "x"}, {"PATH", "GONE"}))
    c = ctx(tmp_path, env=env)
    apply_env(EnvOps((EnvOp("import", (str(script),)),)), c, base_env={"PATH": "/usr/bin:/bin"})
    assert c.env.get("OPAM_SWITCH_PREFIX") == "/o p/default"
    assert c.env.get("PATH") == "/o/bin:/usr/bin:/bin"
    assert "GONE" not in c.env.vars.values and "OPAM_SWITCH_PREFIX" in c.env.vars.exported


# ------------------------------------------------------- oracle: builtins


# ------------------------------------- oracle: every converted plug-in hook

PLUGINS = plugin_files()


@cache
def converted(path: Path):
    reg = Registry(path.parent)
    reg.load_module(path.name)
    res = lift(reg.traces[path.name], set(reg.functions))
    return None if res.issues else res.plugin


def hook_cases():
    """(plugin path, function name, hook name, body) for value/env hooks."""
    cases = []
    for p in PLUGINS:
        pdef = converted(p)
        if pdef is None:
            continue
        for key, body in pdef.hooks.items():
            if isinstance(body, (Values, EnvOps)):
                cases.append((p, key.function_name(p.name), key.hook, body))
    return cases


def fake_prefix(root: Path) -> Path:
    prefix = root / "prefix"
    for d in ("bin", "lib/python3.9/site-packages", "lib/python3.11/site-packages",
              "local/bin", "local/lib/python3.11/dist-packages", "share/gpr",
              "include/openjpeg-2.5", "lib/cmake/openjpeg-2.5", "lib/pkgconfig"):
        (prefix / d).mkdir(parents=True, exist_ok=True)
    now = time.time()
    os.utime(prefix / "lib/python3.9", (now - 50, now - 50))
    return prefix


SETUP = r"""
cd "$5"
SCBI_PLUGINS="$1"
export SCBI_CMAKE_BUILD_TYPE=Debug SCBI_TARGET SCBI_HOST
SCBI_MODVER=([lib2]="lib2:2.0.1" ["$2"]="$2:1.2.3")
SCBI_MODULES_LIST=("$2")
declare -A SCBI_MODULES_DIR=(["$2"]="$6/install" ["$2@build"]="$6/build" ["$2@src"]="$6/src")
load-module "$2" > /dev/null 2>&1
SCBI_ENV_MODULE=$PWD/env-$BASHPID.cmd
: > $SCBI_ENV_MODULE
"""

DUMP_VARS = r"""
for __v in $(compgen -v); do
  [[ $__v == __* ]] && continue
  __d=$(declare -p $__v 2>/dev/null) || continue
  __a=${__d#declare -}; __a=${__a%% *}
  [[ $__a == *[aA]* ]] && continue
  __x=0; [[ $__a == *x* ]] && __x=1
  printf '%s\x1e%s\x1e%s\x1f' "$__v" "$__x" "${!__v}"
done
"""

TEMPLATE = SETUP + DUMP_VARS + r"""
printf '\x1d'
if [[ $4 == value ]]; then
  "$3" "$6" x86_64-linux-gnu default BRANCH 7.8.1
else
  "$3" "$6" x86_64-linux-gnu default > /dev/null
  printf '\x1d'
  for __v in $(compgen -e); do printf '%s\x1e%s\x1f' "$__v" "${!__v}"; done
  printf '\x1d%s' "$(< $SCBI_ENV_MODULE)"
fi
"""


def test_new_operators_and_builtins(tmp_path):
    (tmp_path / "bin").mkdir()
    tool = tmp_path / "bin" / "mytool"
    tool.write_text("#!/bin/sh\necho out $1\n")
    tool.chmod(0o755)
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / ".store").write_text("PYPIURL https://pypi.example/simple\nOTHER x\n")
    sv = ShellVars({"D": "1", "E": "", "V": "3.12", "U": "C:/x", "PATH": f"{tmp_path}/bin:/usr/bin",
                    "SCBI_PLUGINS": str(plugins)}, {"PATH"})
    c = ctx(tmp_path, env=Environment(sv))
    assert expand("${D:+-DX=ON}|${E:+-DX=ON}|${NOPE:+x}", c) == "-DX=ON||"
    assert expand("${V/./}|${V//1/9}|${U/C:/\\/c}", c) == "312|3.92|/c/x"
    assert expand("$(command-path mytool)", c) == f"{tool}"
    assert expand("$(command-path nope-tool)", c) == ""
    assert expand("$(output mytool a)", c) == "out a"
    assert expand("$(store-key PYPIURL)|$(store-key NOPE)", c) == "https://pypi.example/simple|"
    assert expand("$(dirname /a/b/c)|$(dirname c)", c) == "/a/b|."
    #  as the Bash version: the base name when not found
    assert builtins.get_os_lib(c, "nope/libnope.so") == "libnope.so"


def test_empty_condition(tmp_path):
    c = ctx(tmp_path, env=Environment(ShellVars({"A": "x", "B": ""})))
    values = Values(("a", Guarded("empty($B)", ("b",)), Guarded("not empty($A)", ("c",)),
                     Guarded("empty($A)", ("d",))))
    assert eval_values(values, c) == ["a", "b", "c"]


def test_replace_in_values(tmp_path):
    c = ctx(tmp_path, env=Environment(ShellVars({"V": "3.12"})))
    assert expand("libpython$(replace $V . '')|$(replace $V .3 _4)", c) == "libpython312|4_12"


def test_get_version_of_a_plugin(tmp_path):
    c = ctx(tmp_path, plan=PlanState({"lib2": "lib2:2.0.1", "m": "m:1.2"}))
    #  not in the build plan: NONE (as the condition version())
    assert expand("$(get-version lib2)|$(get-version nope)", c) == "2.0.1|NONE"


def test_variables_in_patterns(tmp_path):
    c = ctx(tmp_path, params={"PREFIX": "/opt/x"},
            env=Environment(ShellVars({"V": "/opt/x/lib/a.so", "E": "", "D": "dflt"})))
    assert expand("${V#$PREFIX/}|${V/$PREFIX/@}|${V//\\//:}|${E:-$D}|${V%/$(basename $V)}", c) == \
        "lib/a.so|@/lib/a.so|:opt:x:lib:a.so|dflt|/opt/x/lib"
    #  \$: a literal $, as in Bash
    assert expand("${V/$PREFIX/\\$ROOT}|${E:-\\$D}", c) == "$ROOT/lib/a.so|$D"


def test_plugin_variables(tmp_path):
    #  vars: expanded in the context of the hook, in order, seen by the
    #  values and the environment actions; the own ones override the
    #  inherited ones
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "base.yaml").write_text("vars:\n  A: base\n  B: b-$A\n")
    (plugins / "m.yaml").write_text(
        "inherit:\n  - from: base\n"
        "vars:\n  A: own\n  DOC: $(is-enabled doc ON OFF)\n  OPT: -DDOC=$DOC\n")
    reg = Registry(plugins)
    assert reg.load_module("m")
    assert reg.plugin_variables("m") == {"A": "own", "B": "b-$A", "DOC": "$(is-enabled doc ON OFF)",
                                         "OPT": "-DDOC=$DOC"}
    assert reg.plugin_variables("base") == {"A": "base", "B": "b-$A"}
    c = ctx(tmp_path, env=Environment(ShellVars({"SCBI_doc_SET": "true"})))
    assert set_plugin_vars(c, reg.plugin_variables("m")) == {
        "A": "own", "B": "b-own", "DOC": "ON", "OPT": "-DDOC=ON"}
    assert eval_values(Values(("$OPT", "${A:+-DA=$A}")), c) == ["-DDOC=ON", "-DA=own"]
    apply_env(EnvOps((EnvOp("set-var", ("V", "$B")),)), c)
    assert c.env.get("V") == "b-own"
    #  a local variable or a parameter hides a plug-in variable
    c.params = {"A": "param"}
    assert expand("$A", c) == "param"
    c = ctx(tmp_path)
    assert set_plugin_vars(c, reg.plugin_variables("m"))["OPT"] == "-DDOC=OFF"
