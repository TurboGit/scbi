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
from scbi.hooks.evaluate import apply_env, eval_values
from scbi.hooks.expand import ExpandError, check, expand
from scbi.plan import PlanState
from scbi.plugin import catalog
from scbi.plugin.lift import lift
from scbi.plugin.model import EnvOps, Values
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


@pytest.mark.oracle
def test_builtins_oracle(oracle, tmp_path):
    root = tmp_path / "tree"
    for d in ("lib/python3.9", "lib/python3.11/site-packages", "lib/python3.12", "include/openjpeg-2.5"):
        (root / d).mkdir(parents=True)
    (root / "include" / "openjpeg-2.5" / "openjpeg.h").write_text("")
    now = time.time()
    for i, d in enumerate(("lib/python3.12", "lib/python3.9", "lib/python3.11")):
        os.utime(root / d, (now - 100 + i, now - 100 + i))
    cases = [
        f"last-modified-directory {root}/lib/python*",
        f"last-modified-directory '{root}/lib/python*'",
        f"last-modified-directory {root}/nothing*",
        f"last-modified-directory {root}/include/open*",
        "get-os-inc-dir stdio.h",
        "get-os-inc-dir sys/types.h",
        "get-os-inc-dir 'python3*/Python.h'",
        "get-os-inc-dir nothere.h",
        f"basename {root}/lib/",
        "basename /a/b.tar.gz .gz",
        f"ls {root}/lib",
        f"ls {root}/include/openjpeg-2.5/openjpeg.h {root}/lib",
    ]
    outputs = oracle.batch('cd "$2"; eval "$1"', [(c, str(tmp_path)) for c in cases])
    c = ctx(tmp_path)
    for case, out in zip(cases, outputs):
        assert expand(f"$({case})", c) == " ".join(out.split()), case


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


@pytest.mark.oracle
def test_converted_hooks_oracle(oracle, tmp_path):
    prefix = fake_prefix(tmp_path)
    cases = hook_cases()
    assert len(cases) > 700
    outputs = oracle.batch(
        TEMPLATE,
        [(str(p.parent), p.name, fname, "value" if isinstance(b, Values) else "env",
          str(tmp_path), str(prefix)) for p, fname, _, b in cases],
    )
    checked = 0
    for (p, fname, hook, body), out in zip(cases, outputs):
        parts = out.split("\x1d")
        assert len(parts) == (2 if isinstance(body, Values) else 4), (p, fname, out[-300:])
        before = ShellVars()
        for rec in parts[0].split("\x1f")[:-1]:
            name, x, value = rec.split("\x1e")
            before.set(name, value, export=x == "1")
        record = tmp_path / f"py-{checked}.cmd"
        record.write_text("")
        c = HookContext(
            module=p.name, variant="default", hook=hook,
            params=dict(zip(catalog.spec(hook).params,
                            [str(prefix), HOST, "default", "BRANCH", "7.8.1"])),
            env=Environment(before, record=record),
            plan=PlanState({"lib2": "lib2:2.0.1", p.name: f"{p.name}:1.2.3"}),
            modules_list=[p.name], host=HOST, target=HOST, cwd=tmp_path,
            scbi_bdir=before.values.get("SCBI_BDIR", ""),
            arrays={"SCBI_MODULES_DIR": {p.name: f"{prefix}/install", f"{p.name}@build": f"{prefix}/build",
                                         f"{p.name}@src": f"{prefix}/src"}},
        )
        where = (p.parent.parent.name, fname)
        if isinstance(body, Values):
            lines = parts[1].split("\n")[:-1] if parts[1] else []
            assert eval_values(body, c) == [" ".join(ln.split()) for ln in lines], where
        else:
            apply_env(body, c, base_env={"PATH": os.environ["PATH"]})
            after = dict(rec.split("\x1e") for rec in parts[2].split("\x1f")[:-1])
            assert c.env.environ() == after, where
            assert record.read_text().rstrip("\n") == parts[3], where
        checked += 1
    assert checked == len(cases)
