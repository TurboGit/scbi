"""Execution of hooks in Bash (scbi.hooks.exec, scbi.hooks.runtime)."""

import os
import re
from pathlib import Path

import pytest

from corpus import plugin_files
from oracle import REPO_ROOT, extract_functions
from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.context import HookContext
from scbi.hooks.exec import HookShell
from scbi.hooks.runtime import COMPAT, load_runtime
from scbi.plan import PlanState
from scbi.plugin import catalog
from scbi.plugin.catalog import ENV, VALUE
from scbi.plugin.lift import parse_hook_name
from scbi.plugin.registry import Registry

HOST = "x86_64-linux-gnu"
BASE_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C", "LC_ALL": "C"}


def driver_vars(root: Path) -> ShellVars:
    """Driver variables set before loading the runtime."""
    return ShellVars({
        "SCBI_HOST": HOST, "SCBI_TARGET": HOST, "SCBI_IS_WINDOWS": "no",
        "SCBI_ROOT": str(root), "SCBI_PLUGINS": str(REPO_ROOT / "scripts.d"),
        "SCBI_JOBS": "2", "SCBI_HALF_JOBS": "1", "DO_QUIET": "no", "HOME": str(root),
    }, {"SCBI_HOST", "SCBI_TARGET", "HOME"})


@pytest.fixture(scope="module")
def runtime(oracle):
    #  same SCBI_ROOT as the oracle, to compare paths
    root = Path(oracle.env()["SCBI_ROOT"])
    root.mkdir(exist_ok=True)
    return load_runtime(REPO_ROOT / "scripts.d", driver_vars(root), cwd=root, base_env=BASE_ENV)


def test_compat_matches_driver():
    driver = extract_functions(REPO_ROOT / "scbi")
    for definition in re.findall(r"^function .*?^}", COMPAT.read_text(), re.S | re.M):
        assert definition in driver, definition.split("\n")[0]


def test_runtime(runtime, tmp_path):
    assert "define-var" in runtime.functions and "get-config-options" in runtime.functions
    assert runtime.vars.values["SCBI_BDIR"].endswith("/root/builds")
    #  testsuite override of 1_setup: .root under the current directory
    sv = driver_vars(tmp_path)
    del sv.values["SCBI_ROOT"]
    tests_rt = load_runtime(REPO_ROOT / "tests" / "scripts.d", sv, cwd=tmp_path, base_env=BASE_ENV)
    assert tests_rt.vars.values["SCBI_BDIR"] == f"{tmp_path}/.root/builds"


YAML_PLUGIN = """
config-options:
  common: [--prefix=$PREFIX]
  fast: [-O3]
config: |
  local OPTIONS=()
  get-config-options OPTIONS $PREFIX $TARGET $VARIANT
  echo configure "${OPTIONS[@]}" for $VARIANT
  helper one two
  echo version $(get-version)
build: exit 3
functions:
  helper:
    params: [A, B]
    run: echo helper $B $A
"""


def ctx_for(module, variant="default", hook="config", **kw) -> HookContext:
    c = HookContext(module=module, variant=variant, hook=hook, host=HOST, target=HOST,
                    plan=PlanState({module: f"{module}/{variant}:1.4"}), modules_list=[module],
                    env=Environment(ShellVars({"PATH": BASE_ENV["PATH"]}, {"PATH"})))
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_run_yaml_command_hook(runtime, tmp_path):
    (tmp_path / "y.yaml").write_text(YAML_PLUGIN)
    reg = Registry(tmp_path)
    assert reg.load_module("y")
    shell = HookShell(runtime, reg.functions, BASE_ENV)
    #  y handled as a dependency of top (with only y, get-version reads
    #  SCBI_MODULES_LIST[-2] and Bash reports a bad array subscript)
    c = ctx_for("y", "fast", cwd=tmp_path, modules_list=["top", "y"])
    res = shell.run(c, "y-config", ["/opt/y", HOST, "fast"])
    assert res.returncode == 0, res.output
    assert res.output.split("\n") == [
        "configure --prefix=/opt/y -O3 for fast", "helper two one", "version 1.4"]
    lines = []
    assert shell.run(c, "y-build", ["/opt/y", HOST, "fast"], on_line=lines.append).returncode == 3


def test_env_file_function(runtime, tmp_path):
    c = ctx_for("y", cwd=tmp_path)
    c.env.vars.functions["module-final-step"] = "module-final-step () \n{ \n    echo final $4\n}"
    res = HookShell(runtime, {}, BASE_ENV).run(c, "module-final-step", ["p", "t", "v", "mod"])
    assert res.output == "final mod"


# ------------------------------------------- oracle: legacy hooks via shells

SETUP = r"""
cd "$5"
SCBI_PLUGINS="$1"
SCBI_MODVER=([lib2]="lib2:2.0.1" ["$2"]="$2:1.2.3")
SCBI_MODULES_LIST=("$2")
declare -A SCBI_MODULES_DIR=()
load-module "$2" > /dev/null 2>&1
"""

TEMPLATE = SETUP + r"""
if [[ $4 == value ]]; then
  "$3" "$6" x86_64-linux-gnu default BRANCH 7.8.1 2>/dev/null
else
  __before=" $(for v in $(compgen -e); do printf '%s=%s ' $v "${!v}"; done)"
  "$3" "$6" x86_64-linux-gnu default > /dev/null 2>&1
  for __v in $(compgen -e); do printf '%s\x1e%s\x1f' "$__v" "${!__v}"; done
fi
"""


def legacy_cases():
    cases = []
    for p in plugin_files():
        reg = Registry(p.parent)
        reg.load_module(p.name)
        for name in reg.traces[p.name].functions:
            key = parse_hook_name(p.name, name)
            if key and catalog.spec(key.hook).kind in (VALUE, ENV) and key.hook != "version":
                cases.append((p, reg, name, key.hook))
    return cases


@pytest.mark.oracle
def test_legacy_hooks_through_shell_oracle(oracle, runtime, tmp_path):
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    cases = legacy_cases()
    assert len(cases) > 800
    kinds = ["value" if catalog.spec(h).kind == VALUE else "env" for _, _, _, h in cases]
    outputs = oracle.batch(
        TEMPLATE,
        [(str(p.parent), p.name, name, k, str(tmp_path), str(prefix))
         for (p, _, name, _), k in zip(cases, kinds)],
    )
    #  Bash environment of the oracle before a hook, as the hook context
    base = dict(rec.split("\x1e") for rec in oracle.call(
        'cd ' + str(tmp_path) + '\nfor v in $(compgen -e); do printf "%s\\x1e%s\\x1f" $v "${!v}"; done'
    ).split("\x1f")[:-1])
    for (p, reg, name, hook), kind, out in zip(cases, kinds, outputs):
        shell = HookShell(runtime, reg.functions, BASE_ENV)
        c = HookContext(module=p.name, variant="default", hook=hook, host=HOST, target=HOST,
                        cwd=tmp_path, modules_list=[p.name],
                        plan=PlanState({"lib2": "lib2:2.0.1", p.name: f"{p.name}:1.2.3"}),
                        env=Environment(ShellVars(dict(base), set(base))))
        args = [str(prefix), HOST, "default", "BRANCH", "7.8.1"]
        if kind == "value":
            assert shell.capture(c, name, args) == (out.split("\n")[:-1] if out else []), name
        else:
            shell.env(c, name, args[:3])
            after = dict(rec.split("\x1e") for rec in out.split("\x1f")[:-1])
            assert {k: v for k, v in c.env.environ().items() if not k.startswith(("OLDPWD", "PWD", "SHLVL", "_"))} == \
                {k: v for k, v in after.items() if not k.startswith(("OLDPWD", "PWD", "SHLVL", "_"))}, name
