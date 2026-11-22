"""List values in the vars of a plug-in."""

import os
from pathlib import Path

import pytest

from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.cmdlang import Runner, State, parse
from scbi.hooks.context import HookContext
from scbi.hooks.evaluate import eval_values, set_plugin_vars
from scbi.hooks.expand import expand
from scbi.plugin import yamlfmt
from scbi.plugin.lint import WARNING, lint_text
from scbi.plugin.model import Values
from scbi.plugin.registry import Registry
from scbi.plugin.yamlwrite import format_text

TEXT = """plugin: p

vars:
  GOPTS:
    - -XBUILD=PROD
    - --target=$TARGET
  NAME: text
"""


def ctx(tmp_path, env=None) -> HookContext:
    return HookContext(module="p", variant="default", hook="build",
                       params={"PREFIX": "/inst", "TARGET": "x86_64", "VARIANT": "default"},
                       env=Environment(ShellVars(env or {})), host="x86_64", target="x86_64", cwd=tmp_path)


def test_yaml(tmp_path):
    f = tmp_path / "p.yaml"
    f.write_text(TEXT)
    pdef = yamlfmt.load(f)
    assert pdef.variables == {"GOPTS": ("-XBUILD=PROD", "--target=$TARGET"), "NAME": "text"}
    assert yamlfmt.to_data(pdef)["vars"] == {"GOPTS": ["-XBUILD=PROD", "--target=$TARGET"], "NAME": "text"}
    assert format_text("p", TEXT) == TEXT
    f.write_text("plugin: p\nvars:\n  L: [a, {b: c}]\n")
    with pytest.raises(yamlfmt.FormatError, match="vars.L: a text or a list of texts"):
        yamlfmt.load(f)


def test_expansion(tmp_path):
    c = ctx(tmp_path, {"SCBI_doc_SET": "true"})
    values = set_plugin_vars(c, {
        "G": ("-XBUILD=PROD", "--target=$TARGET", "$(is-enabled debug -g)", "$(is-enabled doc --doc)"),
        "S": "opts: $G",
    })
    #  a list for the command hooks (the empty item dropped), joined for
    #  the expansions; a scalar var using the list
    assert values == {"G": ["-XBUILD=PROD", "--target=x86_64", "--doc"], "S": "opts: -XBUILD=PROD --target=x86_64 --doc"}
    assert expand("[$G]", c) == "[-XBUILD=PROD --target=x86_64 --doc]"
    assert eval_values(Values(("-DOPTS=$G",)), c) == ["-DOPTS=-XBUILD=PROD --target=x86_64 --doc"]


def run(tmp_path, variables, text):
    out = []
    c = ctx(tmp_path)
    state = State(set_plugin_vars(c, variables), {"PATH": os.environ["PATH"]}, str(tmp_path), out.append,
                  out.append)
    Runner(c, "p.yaml: build").run(parse(text, 1), state)
    return "".join(out)


def test_command_hook(tmp_path):
    variables = {"G": ("-XBUILD=PROD", "--target=$TARGET", "a b")}
    #  a word per item (an item with a blank stays one word)
    assert run(tmp_path, variables, "printf '<%s>' $G\necho") == "<-XBUILD=PROD><--target=x86_64><a b>\n"
    #  += in a hook: for this hook only (each hook gets the vars again)
    assert run(tmp_path, variables, "G += --prefix=$PREFIX\nprintf '<%s>' $G\necho") == \
        "<-XBUILD=PROD><--target=x86_64><a b><--prefix=/inst>\n"
    assert run(tmp_path, variables, "printf '<%s>' $G\necho") == "<-XBUILD=PROD><--target=x86_64><a b>\n"


def test_inheritance(tmp_path):
    (tmp_path / "base.yaml").write_text("plugin: base\nvars:\n  G: [-a, -b]\n  H: [-h]\n")
    (tmp_path / "m.yaml").write_text("plugin: m\ninherit:\n  - from: base\nvars:\n  G: [-own]\n")
    reg = Registry(tmp_path)
    assert reg.load_module("m")
    assert reg.plugin_variables("m") == {"G": ("-own",), "H": ("-h",)}


def test_lint():
    found = [(i.level, i.where, i.message) for i in lint_text("p", TEXT + "  L: [-x, $NOPE, --prefix=$PREFIX]\n")]
    assert found == [(WARNING, "vars.L", "variable NOPE is not known in this hook")]
