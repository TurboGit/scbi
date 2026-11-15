import shutil
from functools import cache
from pathlib import Path

import pytest

from corpus import REPO_ROOT, plugin_files
from scbi.plugin import yamlfmt
from scbi.plugin.catalog import spec, step_names
from scbi.plugin.expr import ExprError, evaluate, parse
from scbi.plugin.legacy import trace_plugin
from scbi.plugin.lift import lift
from scbi.plugin.model import EnvOp, EnvOps, Guarded, HookKey, Commands, Values
from scbi.plugin.registry import Registry
from scbi.plugin.resolve import get_hook, variant_hooks

GMP = """
plugin: c-gmp
with-variants:
  native:
    packages: ["os@-gmp-dev:[v]"]
    env: [set-var GMP_INCLUDE_DIR /usr/include]
vcs: {proxy: default, options: none, protocol: mercurial, url: "https://gmplib.org/repo/gmp/"}
archive:
  proxy: default
  options: none
  protocol: curl
  url: https://gmplib.org/download/gmp
  file: gmp-$VERSION.tar.xz
build-depends: [c-sandbox]
depends:
  vcs: [os@-autotools-dev, os@-automake]
env:
  - add-to-var C_INCLUDE_PATH $PREFIX/include
  - if target =~ mingw32: set-var OS Windows_NT
out-of-tree: false
pre-config:
  vcs: ./.bootstrap
config:
  _: ./configure --prefix=$PREFIX
  vcs: ./configure --enable-maintainer-mode --prefix=$PREFIX
  cross:
    _: ./configure --prefix=$PREFIX/$TARGET --build=$SCBI_HOST --host=$TARGET
    vcs: |
      ./configure --enable-maintainer-mode --prefix=$PREFIX/$TARGET \\
                  --build=$SCBI_HOST --host=$TARGET
build: make -j$JOBS
install: make install
"""


def test_load_yaml(tmp_path):
    p = tmp_path / "c-gmp.yaml"
    p.write_text(GMP)
    d = yamlfmt.load(p)
    assert d.hooks[HookKey("vcs")] == Values(("default", "none", "mercurial", "https://gmplib.org/repo/gmp/"))
    assert d.hooks[HookKey("archive")].items[-1] == "gmp-$VERSION.tar.xz"
    assert d.hooks[HookKey("out-of-tree")] == Values(("false",))
    assert d.hooks[HookKey("depends", "vcs")] == Values(("os@-autotools-dev", "os@-automake"))
    assert d.hooks[HookKey("env")] == EnvOps((
        EnvOp("add-to-var", ("C_INCLUDE_PATH", "$PREFIX/include")),
        Guarded("target =~ mingw32", (EnvOp("set-var", ("OS", "Windows_NT")),)),
    ))
    assert d.hooks[HookKey("config", "vcs", True)].script.endswith("--host=$TARGET")
    assert d.hooks[HookKey("pre-config", "vcs")] == Commands("./.bootstrap")
    assert d.with_variants[0].packages == ("os@-gmp-dev:[v]",)
    assert d.function_names() >= {"c-gmp-config", "c-gmp-vcs-cross-config", "c-gmp-vcs-depends"}


@pytest.mark.parametrize(
    "text, message",
    [
        ("plugin: other\n", "does not match"),
        ("nothook: x\n", "unknown hook"),
        ("config: [a]\n", "command language"),
        ("env: [frobnicate X]\n", "unknown environment action"),
        ("config: {common: x}\n", "only allowed for cumulative"),
        ("depends: [{if version(: x}]\n", "condition"),
        ("vcs: {proxy: default, url: x}\n", "missing fields"),
    ],
)
def test_format_errors(tmp_path, text, message):
    p = tmp_path / "p.yaml"
    p.write_text(text)
    with pytest.raises(yamlfmt.FormatError, match=message):
        yamlfmt.load(p)


def test_scalars_are_strings(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text("out-of-tree: no\nconfig-options: [1.10, yes, ~]\n")
    d = yamlfmt.load(p)
    assert d.hooks[HookKey("out-of-tree")] == Values(("no",))
    assert d.hooks[HookKey("config-options")] == Values(("1.10", "yes", "~"))


# ----------------------------------------------------------- conditions


class Ctx:
    def __init__(self, **kw):
        self.kw = kw

    def variable(self, name):
        return self.kw.get(name, "")

    def function(self, name, arg):
        return self.kw.get(f"{name}({arg})", "")

    def has_discriminants(self, discs):
        return all(d in self.kw.get("discs", ()) for d in discs)

    def expand(self, value):
        return value


@pytest.mark.parametrize(
    "cond, expected",
    [
        ("ref =~ ^7.8", True),
        ("ref == 7.8.1", True),
        ("version(lib2) > 1.9", True),
        ("version(lib2) < 1.9", False),
        ("not (version(lib2) =~ 2.0)", False),
        ("cross", False),
        ("not cross and target =~ linux", True),
        ("on deb,12 or on fed", True),
        ("on deb,9", False),
        ("kind == true", False),
        ('target == "x86_64-linux-gnu"', True),
        ("exists(toto)", False),
    ],
)
def test_conditions(cond, expected):
    ctx = Ctx(ref="7.8.1", target="x86_64-linux-gnu", cross=False, kind="false",
              discs=("deb", "12"), **{"version(lib2)": "2.0.1"})
    assert evaluate(cond, ctx) is expected


@pytest.mark.parametrize("cond", ["", "ref ==", "(ref", "version(lib2", "ref == a b"])
def test_condition_errors(cond):
    with pytest.raises(ExprError):
        parse(cond)


# -------------------------------------------- conversion of all plug-ins

PLUGINS = plugin_files()


@cache
def lifted(path: Path):
    reg = Registry(path.parent)
    reg.load_module(path.name)
    return lift(reg.traces[path.name], set(reg.functions))


def convertible() -> list[Path]:
    return [p for p in PLUGINS if not lifted(p).issues]


def test_most_plugins_convertible():
    assert len(convertible()) > 140


@pytest.mark.parametrize("path", PLUGINS, ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_yaml_round_trip(path, tmp_path):
    res = lifted(path)
    if res.issues:
        pytest.skip("; ".join(f"{i.function}: {i.message}" for i in res.issues)[:200])
    f = tmp_path / f"{path.name}.yaml"
    f.write_text(yamlfmt.dump(res.plugin))
    assert yamlfmt.load(f) == res.plugin


@pytest.fixture(scope="module")
def converted_dirs(tmp_path_factory):
    """Copy of each plug-in directory with convertible plug-ins in YAML."""
    dirs = {}
    for src in sorted({p.parent for p in PLUGINS}):
        dst = tmp_path_factory.mktemp(src.parent.name)
        for p in PLUGINS:
            if p.parent != src:
                continue
            res = lifted(p)
            if res.issues:
                shutil.copy(p, dst / p.name)
            else:
                (dst / f"{p.name}.yaml").write_text(yamlfmt.dump(res.plugin))
        dirs[src] = dst
    return dirs


def variants_of(names, plugin):
    steps = sorted(step_names(), key=len, reverse=True)
    found = set()
    for n in names:
        if n.startswith(f"{plugin}-"):
            rest = n[len(plugin) + 1 :]
            for s in steps:
                if rest.endswith(f"-{s}"):
                    q = rest[: -len(s) - 1].removesuffix("-cross")
                    if q and q != "cross":
                        found.add(q)
                    break
    found = sorted(found)
    return ["default", "native"] + found + ([f"{found[0]}.{found[1]}"] if len(found) > 1 else [])


def test_yaml_namespace_and_resolution(converted_dirs):
    """Plug-ins loaded from YAML define the same hooks as the legacy ones,
    hence the same resolution for every hook, variant and cross mode."""
    for p in PLUGINS:
        legacy = Registry(p.parent)
        assert legacy.load_module(p.name)
        yaml_reg = Registry(converted_dirs[p.parent])
        assert yaml_reg.load_module(p.name)
        #  composite Bash hooks are replaced by "variants:"
        composite = lifted(p).composite if not lifted(p).issues else {}

        def effective(functions):
            out = []
            for f in functions:
                for g in composite.get(f, [f]):
                    if g and g not in out:
                        out.append(g)
            return out

        assert set(yaml_reg.functions) == set(legacy.functions) - set(composite), p
        for v in variants_of(legacy.functions, p.name):
            for h in step_names():
                for cross in (False, True):
                    if spec(h).cumulative:
                        #  same functions, duplicates aside (a variant listed
                        #  twice calls its hook once with "variants:")
                        assert effective(variant_hooks(yaml_reg, p.name, h, v, cross)) == \
                            effective(variant_hooks(legacy, p.name, h, v, cross)), (p, v, h, cross)
                    else:
                        assert [x for x in [get_hook(yaml_reg, p.name, v, h, cross)] if x] == \
                            effective([get_hook(legacy, p.name, v, h, cross)]), (p, v, h, cross)


# ------------------------------------- lifted static values vs Bash output

VALUE_DUMP = r"""
source "$1" > /dev/null 2>&1
for f in $2; do printf '%s\x1e' "$f"; $f /p x86_64-linux-gnu default 2>/dev/null; printf '\x1f'; done
"""


def test_unknown_builtin_rejected(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text("depends: [\"$(cat file)\"]\n")
    with pytest.raises(yamlfmt.FormatError, match="unknown function"):
        yamlfmt.load(p)
    p.write_text("env: [add-to-var PATH $(last-modified-directory $PREFIX/lib/py*)/bin]\n")
    yamlfmt.load(p)


def test_convert_command(tmp_path, capsys):
    from scbi.convert import main

    src = tmp_path / "lib"
    src.write_text("function lib-depends()\n{\n    echo zlib\n}\n"
                   "function lib-build()\n{\n    local PREFIX=$1\n    make\n}\n")
    bad = tmp_path / "bad"
    bad.write_text("function bad-build()\n{\n    local VARIANT=$2\n}\n")
    assert main([str(src), str(bad)]) == 1
    out = capsys.readouterr().out
    assert "bad-build: parameter VARIANT=$2" in out
    assert yamlfmt.load(tmp_path / "lib.yaml").hooks[HookKey("depends")] == Values(("zlib",))
    assert not (tmp_path / "bad.yaml").exists()


# ------------------------------------------------- variants including others


class AliasNs:
    def __init__(self, names, aliases):
        self.names, self.aliases = set(names), aliases

    def fn_exists(self, name):
        return name in self.names

    def variant_members(self, module, variant):
        return self.aliases.get(variant, ())


def test_variant_members_resolution():
    ns = AliasNs(
        ["d-common-depends", "d-ai-depends", "d-hdr-depends", "d-jxl-depends", "d-depends",
         "d-ai-config-options", "d-config", "d-hdr-config", "d-x-config"],
        {"all": ("ai", "hdr", "jxl")},
    )
    assert variant_hooks(ns, "d", "depends", "all") == \
        ["d-common-depends", "d-ai-depends", "d-hdr-depends", "d-jxl-depends"]
    assert variant_hooks(ns, "d", "depends", "all.ai") == variant_hooks(ns, "d", "depends", "all")
    assert variant_hooks(ns, "d", "config-options", "all") == ["d-ai-config-options"]
    assert get_hook(ns, "d", "all", "config") == "d-hdr-config"
    assert get_hook(ns, "d", "x.all", "config") == "d-x-config"
    ns.names.add("d-all-config")
    assert get_hook(ns, "d", "all", "config") == "d-all-config"
    #  default variant unchanged
    assert variant_hooks(ns, "d", "depends", "default") == ["d-common-depends", "d-depends"]


def test_variant_members_cycle():
    ns = AliasNs([], {"a": ("b",), "b": ("a",)})
    with pytest.raises(ValueError, match="cycle"):
        get_hook(ns, "d", "a", "config")


def test_variants_yaml(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("variants:\n  all: [ai, hdr, jxl]\n  big: all\ndepends:\n  ai: [x]\n")
    d = yamlfmt.load(p)
    assert d.variants == {"all": ("ai", "hdr", "jxl"), "big": ("all",)}
    reg = Registry(tmp_path)
    reg.load_module("d")
    assert variant_hooks(reg, "d", "depends", "big") == ["d-ai-depends"]
    p.write_text("variants:\n  all: [a.b]\n")
    with pytest.raises(yamlfmt.FormatError, match="list of variant names"):
        yamlfmt.load(p)


def test_composite_variant_converted():
    #  c-darktable (converted from Bash, its all variant was a composite)
    pdef = yamlfmt.load(REPO_ROOT / "scripts.d" / "c-darktable.yaml")
    assert pdef.variants == {"all": ("ai", "hdr", "jxl")}


def test_composite_not_equivalent_reported(tmp_path):
    #  "all" would also select ai-config, which the Bash all variant did not
    (tmp_path / "m").write_text(
        "function m-ai-depends() { echo a; }\nfunction m-all-depends() { m-ai-depends; }\n"
        "function m-ai-config() { true; }\n")
    reg = Registry(tmp_path)
    reg.load_module("m")
    res = lift(reg.traces["m"], set(reg.functions))
    assert res.issues and "cannot be expressed" in res.issues[0].message


def test_command_bodies_parsed_with_lines(tmp_path):
    from scbi.plugin.model import Commands, HookKey

    p = tmp_path / "p.yaml"
    p.write_text("plugin: p\nconfig: ./configure\nbuild: |\n  make\n  if cross:\n    make cross\n"
                 "functions:\n  f:\n    params: [A]\n    run: |\n      echo $A\n")
    d = yamlfmt.load(p)
    assert d.hooks[HookKey("build")] == Commands("make\nif cross:\n  make cross")
    assert d.hooks[HookKey("build")].line == 4
    assert d.hooks[HookKey("config")].line == 2
    assert d.functions["f"].line == 11
    p.write_text("plugin: p\nbuild: |\n  make\n  if cross\n    x\n")
    with pytest.raises(yamlfmt.FormatError, match=r"build: line 4: .*':'"):
        yamlfmt.load(p)


# ------------------------------------------------- plug-ins of scripts.d


def _repository_plugins():
    from corpus import yaml_plugin_files

    return yaml_plugin_files()


@pytest.mark.parametrize("path", _repository_plugins(), ids=lambda p: p.name)
def test_repository_plugin_valid(path):
    """Each YAML plug-in of scripts.d loads, has no lint error and is in
    the canonical form (scbi format)."""
    from scbi.plugin.lint import lint_text
    from scbi.plugin.yamlwrite import format_text

    yamlfmt.load(path)
    text = path.read_text()
    module = path.name[:-len(".yaml")]
    assert [i for i in lint_text(module, text) if i.level == "error"] == []
    assert format_text(module, text) == text


def test_repository_plugins_count():
    assert len(_repository_plugins()) > 100
