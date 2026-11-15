from pathlib import Path

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
