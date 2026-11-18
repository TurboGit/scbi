"""The plug-in resolved for a module reference and its hashes
(scbi.plugin.resolved): what does not change the build of a module
(comments, formatting, other variants, its env hook) does not change
resolved_md5."""

from pathlib import Path
from types import SimpleNamespace

from scbi.bashenv import ShellVars
from scbi.hooks.runner import HookRunner
from scbi.plan import PlanState
from scbi.plugin.registry import Registry
from scbi.plugin.resolved import env_md5, resolve_module, resolved_md5

BASE = """\
plugin: base

functions:
  helper:
    run: echo helper

install:
  _: make install
  other: make install-other
"""

MOD = """\
plugin: mod

inherit:
  - from: base

config: ../src/configure

env:
  - set-var MOD_ROOT $PREFIX
"""


def driver(plugins: Path, target: str = "x86_64-linux-gnu"):
    values = {"SCBI_TARGET": target, "SCBI_BDIR": "/b", "SCBI_PLUGINS": str(plugins)}
    sv = ShellVars(values, set())
    d = SimpleNamespace(registry=Registry(plugins, read_legacy=False), plan=PlanState(), sv=sv,
                        get=lambda n: values.get(n, ""))
    runner = HookRunner(d.registry, lambda: sv, dict, "x86_64-linux-gnu", target, list, plugins)
    d.runner = lambda: runner
    return d


def hashes(tmp_path, mod: str, base: str = BASE, variant: str = "default") -> tuple[str, str]:
    plugins = tmp_path / f"p{len(list(tmp_path.iterdir()))}"
    plugins.mkdir()
    (plugins / "base.yaml").write_text(base)
    (plugins / "mod.yaml").write_text(mod)
    d = driver(plugins)
    return resolved_md5(d, "mod", variant, "NONE", "NONE"), env_md5(d, "mod", variant)


def test_resolve_module(tmp_path):
    (tmp_path / "base.yaml").write_text(BASE)
    (tmp_path / "mod.yaml").write_text(MOD)
    pdef = resolve_module(driver(tmp_path), "mod", "other", "NONE", "NONE")
    assert set(pdef.functions) == {"helper"}
    assert sorted(k.hook for k in pdef.hooks) == ["config", "env", "install"]


def test_resolved_md5(tmp_path):
    ref = hashes(tmp_path, MOD)
    #  a comment, the formatting, a variant not used: unchanged
    assert hashes(tmp_path, "#  a comment\n" + MOD.replace("config: ../src/configure",
                                                         "config: '../src/configure'")) == ref
    assert hashes(tmp_path, MOD.replace("config: ../src/configure",
                                        "config:\n  _: ../src/configure\n  other: ../src/configure x")) == ref
    #  the hook of another variant of the parent: unchanged
    assert hashes(tmp_path, MOD, BASE.replace("install-other", "install-other2")) == ref
    #  a hook used, a parent hook used, a function: changed
    assert hashes(tmp_path, MOD.replace("configure", "configure --x"))[0] != ref[0]
    assert hashes(tmp_path, MOD, BASE.replace("_: make install", "_: make install2"))[0] != ref[0]
    assert hashes(tmp_path, MOD, BASE.replace("echo helper", "echo helper2"))[0] != ref[0]
    #  the other variant: another plug-in
    assert hashes(tmp_path, MOD, variant="other")[0] != ref[0]


def test_env_md5(tmp_path):
    ref = hashes(tmp_path, MOD)
    #  the env hook is not part of the resolved plug-in of the module...
    changed = hashes(tmp_path, MOD + "  - set-var MOD_X 1\n")
    assert changed[0] == ref[0] and changed[1] != ref[1]
    #  ... an item for another variant changes nothing
    assert hashes(tmp_path, MOD + "  - if variant == other: set-var MOD_X 1\n") == ref
