from pathlib import Path

import pytest

from corpus import plugin_files
from scbi.plugin.catalog import step_names
from scbi.plugin.legacy import trace_plugin
from scbi.plugin.registry import (
    Registry,
    copy_function,
    parse_inherit_args,
    with_variant_functions,
)
from scbi.plugin.resolve import get_hook, variant_hooks

# ---------------------------------------------------------------- unit


def write(d: Path, name: str, text: str) -> Path:
    p = d / name
    p.write_text(text)
    return p


def test_trace_records_calls_in_order(tmp_path):
    p = write(
        tmp_path,
        "child",
        "function child-config() { a; }\n"
        "inherit-plugin parent --hooks=build\n"
        "function child-build() { b; }\n"
        "with-variant native os@-x:[v] --env 'set-var A 1'\n"
        "LIBS=static\n",
    )
    t = trace_plugin(p)
    assert [c.name for c in t.calls] == ["inherit-plugin", "with-variant"]
    assert list(t.calls[0].functions) == ["child-config"]
    assert t.calls[0].args == ["parent", "--hooks=build"]
    assert t.calls[1].args == ["native", "os@-x:[v]", "--env", "set-var A 1"]
    assert set(t.functions) == {"child-config", "child-build"}
    assert t.variables == {"LIBS": "static"}


def test_parse_inherit_args():
    o = parse_inherit_args("p", ["inh-specific", "--hooks=config", "--custom-hooks=shared"])
    assert (o.parent, o.hooks, o.custom_hooks) == ("inh-specific", "config", "shared")
    o = parse_inherit_args("p", ["--no-variant", "--hooks=build", "--hooks", "setup", "test19"])
    assert (o.parent, o.no_variant, o.hooks) == ("test19", True, "build|setup")
    o = parse_inherit_args("p", ["--name", "toto", "postinst"])
    assert (o.parent, o.name) == ("postinst", "toto")


def test_copy_function():
    assert copy_function("a-config () \n{ \n    x\n}", "b-config") == "b-config () \n{ \n    x\n}"


def test_inheritance_order(tmp_path):
    write(tmp_path, "parent", "function parent-config() { p; }\nfunction parent-build() { p; }\n"
                              "function parent-install() { p; }\n")
    write(tmp_path, "child", "function child-config() { c1; }\ninherit-plugin parent\n"
                             "function child-build() { c2; }\n")
    r = Registry(tmp_path)
    assert r.load_module("child")
    assert "c1" in r.functions["child-config"]
    assert "c2" in r.functions["child-build"]
    assert r.functions["child-install"] == "child-install () \n{ \n    p\n}"
    assert r.inherits == {"child": ["parent"]}
    assert r.loaded == {"parent": "yes", "child": "yes"}


def test_with_variant(tmp_path):
    funcs = with_variant_functions("natv", "native", ["pckA:[v]", "NONE", "--env", "set-var R /usr"])
    assert funcs["natv-native-depends"] == "function natv-native-depends() {  echo pckA:[v]; echo ; true; }"
    assert funcs["natv-native-env"] == "function natv-native-env() {  set-var R /usr; true; }"
    assert "natv-native-cross-post-install" in funcs
    assert "natv-native-default-cross-patches" in funcs


class FakeNs:
    def __init__(self, *names):
        self.names = set(names)

    def fn_exists(self, name):
        return name in self.names


def test_resolution():
    ns = FakeNs("m-config", "m-vcs-config", "m-cross-config", "m-vcs-cross-config",
                "m-depends", "m-common-depends", "m-vcs-depends", "m-default-env")
    assert get_hook(ns, "m", "default", "config") == "m-config"
    assert get_hook(ns, "m", "x.vcs", "config") == "m-vcs-config"
    assert get_hook(ns, "m", "default", "config", cross=True) == "m-cross-config"
    assert get_hook(ns, "m", "vcs", "config", cross=True) == "m-vcs-cross-config"
    assert get_hook(ns, "m", "default", "build") == ""
    assert variant_hooks(ns, "m", "depends", "default") == ["m-common-depends", "m-depends"]
    assert variant_hooks(ns, "m", "depends", "vcs") == ["m-common-depends", "m-vcs-depends"]
    assert variant_hooks(ns, "m", "depends", "native") == ["m-depends"]
    assert variant_hooks(ns, "m", "env", "default") == ["m-default-env"]


# --------------------------------------------------------------- oracle

PLUGINS = [p for p in plugin_files()]

LOAD_DUMP = r"""
SCBI_PLUGINS="$2"
__base=" $(compgen -A function | tr '\n' ' ') "
load-module "$1" > /dev/null 2>&1 || echo LOAD-FAILED
for f in $(compgen -A function); do
    [[ $__base == *" $f "* ]] && continue
    printf '%s\x1e%s\x1f' "$f" "$(declare -f "$f")"
done
"""


def bash_functions(out: str) -> dict[str, str]:
    res = {}
    for rec in out.split("\x1f")[:-1]:
        name, definition = rec.split("\x1e", 1)
        res[name.lstrip("\n")] = definition
    return res


CANONICAL = r"""
eval "$1"
for n in $2; do printf '%s\x1e%s\x1f' "$n" "$(declare -f "$n")"; done
"""


def canonical_all(oracle, namespaces: list[dict[str, str]]) -> list[dict[str, str]]:
    """Definitions normalized by Bash (eval then declare -f)."""
    outputs = oracle.batch(
        CANONICAL, [("\n".join(ns.values()), " ".join(ns)) for ns in namespaces]
    )
    return [bash_functions(out) for out in outputs]


@pytest.fixture(scope="module")
def loaded(oracle):
    """(plugin path, Bash namespace, Python registry) for every plug-in."""
    outputs = oracle.batch(LOAD_DUMP, [(p.name, str(p.parent)) for p in PLUGINS])
    result = []
    for p, out in zip(PLUGINS, outputs):
        reg = Registry(p.parent)
        assert reg.load_module(p.name), p
        result.append((p, bash_functions(out), reg))
    return result


@pytest.mark.oracle
def test_load_module_namespace_oracle(oracle, loaded):
    assert len(loaded) > 150
    for p, bash, reg in loaded:
        assert set(reg.functions) == set(bash), p
    canon = canonical_all(oracle, [reg.functions for _, _, reg in loaded])
    for (p, bash, _), python in zip(loaded, canon):
        assert python == bash, p


def candidate_variants(plugin: str, names) -> list[str]:
    steps = sorted(step_names(), key=len, reverse=True)
    found = set()
    for n in names:
        if not n.startswith(f"{plugin}-"):
            continue
        rest = n[len(plugin) + 1 :]
        for s in steps:
            if rest.endswith(f"-{s}"):
                q = rest[: -len(s) - 1]
                q = q[: -len("-cross")] if q.endswith("-cross") else q
                if q and q != "cross":
                    found.add(q)
                break
    found = sorted(found)
    combos = [f"{found[0]}.{found[1]}", f"{found[1]}.{found[0]}"] if len(found) > 1 else []
    return ["default", "native", "nosuchvariant"] + found + combos


RESOLVE = r"""
SCBI_PLUGINS="$2"
load-module "$1" > /dev/null 2>&1
for SCBI_TARGET in $SCBI_HOST arm-linux-gnueabi; do
  for v in $3; do
    for h in $4; do
      get-hook R "$1" $v $h
      V=()
      plugin-get-variant-hooks V "$1" $h x x $v
      printf '%s|%s|%s|%s|%s\n' "$SCBI_TARGET" $v $h "$R" "${V[*]}"
    done
  done
done
"""


@pytest.mark.oracle
def test_resolution_oracle(oracle, loaded):
    hooks = " ".join(step_names())
    cases = []
    for p, bash, reg in loaded:
        cases.append((p.name, str(p.parent), " ".join(candidate_variants(p.name, bash)), hooks))
    outputs = oracle.batch(RESOLVE, cases)
    checked = 0
    for (case, out), (p, _, reg) in zip(zip(cases, outputs), loaded):
        for line in out.splitlines():
            target, v, h, hook, hooks_list = line.split("|")
            cross = target != oracle.host
            assert get_hook(reg, p.name, v, h, cross) == hook, (p.name, v, h, cross)
            assert variant_hooks(reg, p.name, h, v, cross) == hooks_list.split(), (p.name, v, h, cross)
            checked += 1
    assert checked > 10000
