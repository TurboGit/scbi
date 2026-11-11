import shutil
from functools import cache
from pathlib import Path

import pytest

from corpus import plugin_files
from scbi.plugin import yamlfmt
from scbi.plugin.catalog import step_names
from scbi.plugin.expr import ExprError, evaluate, parse
from scbi.plugin.legacy import trace_plugin
from scbi.plugin.lift import lift
from scbi.plugin.model import EnvOp, EnvOps, Guarded, HookKey, Shell, Values
from scbi.plugin.registry import Registry
from scbi.plugin.resolve import get_hook, variant_hooks

GMP = """
plugin: c-gmp
os-variants:
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
    assert d.hooks[HookKey("pre-config", "vcs")] == Shell("./.bootstrap")
    assert d.os_variants[0].packages == ("os@-gmp-dev:[v]",)
    assert d.function_names() >= {"c-gmp-config", "c-gmp-vcs-cross-config", "c-gmp-vcs-depends"}


@pytest.mark.parametrize(
    "text, message",
    [
        ("plugin: other\n", "does not match"),
        ("nothook: x\n", "unknown hook"),
        ("config: [a]\n", "shell script"),
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
    return lift(trace_plugin(path))


def convertible() -> list[Path]:
    return [p for p in PLUGINS if not lifted(p).issues]


def test_most_plugins_convertible():
    assert len(convertible()) > 250


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
        assert set(yaml_reg.functions) == set(legacy.functions), p
        for v in variants_of(legacy.functions, p.name):
            for h in step_names():
                for cross in (False, True):
                    assert get_hook(yaml_reg, p.name, v, h, cross) == get_hook(legacy, p.name, v, h, cross)
                    assert variant_hooks(yaml_reg, p.name, h, v, cross) == variant_hooks(legacy, p.name, h, v, cross)


# ------------------------------------- lifted static values vs Bash output

VALUE_DUMP = r"""
source "$1" > /dev/null 2>&1
for f in $2; do printf '%s\x1e' "$f"; $f /p x86_64-linux-gnu default 2>/dev/null; printf '\x1f'; done
"""


@pytest.mark.oracle
def test_static_values_oracle(oracle):
    """Values without variables or guards are exactly the hook output."""
    cases, expected = [], []
    for p in convertible():
        static = {}
        for key, body in lifted(p).plugin.hooks.items():
            if isinstance(body, Values) and all(isinstance(i, str) and "$" not in i for i in body.items):
                static[key.function_name(p.name)] = list(body.items)
        if static:
            cases.append((str(p), " ".join(static)))
            expected.append(static)
    outputs = oracle.batch(VALUE_DUMP, cases)
    checked = 0
    for (path, _), static, out in zip(cases, expected, outputs):
        for rec in out.split("\x1f")[:-1]:
            name, text = rec.split("\x1e", 1)
            lines = text.split("\n")[:-1] if text else []
            assert static[name] == lines, (path, name)
            checked += 1
    assert checked > 500


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
