"""Plug-in file formats (scbi.plugin.formats): the driver only uses the
format-independent model; a new format is a reader built on
scbi.plugin.construct and an entry in formats.FORMATS."""

import json
from pathlib import Path

import pytest

from scbi.plugin import construct, formats
from scbi.plugin.model import Commands, EnvOps, HookKey, PluginDef, Values
from scbi.plugin.registry import Registry
from scbi.plugin.resolve import get_hook, variant_hooks


def test_find_and_names(tmp_path):
    (tmp_path / "a").write_text("")           # a legacy Bash plug-in
    (tmp_path / "b.yaml").write_text("plugin: b\n")
    assert formats.find(tmp_path, "a") is None
    assert formats.find(tmp_path, "b") == tmp_path / "b.yaml"
    assert formats.format_of("b.yaml").name == "yaml"
    assert formats.format_of("a") is None and formats.format_of(".yaml") is None
    assert formats.module_name("dir/c-x.yaml") == "c-x"
    with pytest.raises(formats.PluginFormatError):
        formats.load(tmp_path / "a")


def _json_load(path: Path) -> PluginDef:
    """A minimal reader of another syntax: {"hooks": {"<hook>[:<qualifier>]": ...}}."""
    data = json.loads(path.read_text())
    pdef = PluginDef(path.name[: -len(".json")])
    for name, body in data["hooks"].items():
        hook, _, qualifier = name.partition(":")
        try:
            construct.check_qualifier(hook, qualifier)
            if hook in ("config", "build"):
                obj = construct.commands(body)
            elif hook == "env":
                obj = EnvOps(tuple(construct.env_action(a) for a in body))
            elif isinstance(body, dict):
                obj = construct.record(hook, body)
            else:
                obj = Values(tuple(construct.value(v) for v in body))
        except construct.DefinitionError as e:
            raise formats.PluginFormatError(f"{path}: {name}: {e}") from None
        pdef.hooks[HookKey(hook, qualifier)] = obj
    return pdef


def test_another_format(tmp_path, monkeypatch):
    monkeypatch.setattr(formats, "FORMATS", formats.FORMATS + (formats.Format("json", ".json", _json_load),))
    (tmp_path / "j.json").write_text(json.dumps({"hooks": {
        "vcs": {"proxy": "none", "options": "none", "protocol": "git", "url": "/r/j.git"},
        "depends:common": ["lib1"], "depends:fast": ["lib2"],
        "env": ["add-to-var PATH $PREFIX/bin"],
        "build": "make -j$SCBI_JOBS\nif cross:\n    make cross",
    }}))
    reg = Registry(tmp_path)
    assert reg.plugin_file("j") == tmp_path / "j.json"
    assert reg.load_module("j")
    assert reg.functions["j-vcs"] == Values(("none", "none", "git", "/r/j.git"))
    assert isinstance(reg.functions["j-build"], Commands) and reg.functions["j-build"].ast
    assert get_hook(reg, "j", "default", "build") == "j-build"
    assert variant_hooks(reg, "j", "depends", "fast") == ["j-common-depends", "j-fast-depends"]
    (tmp_path / "k.json").write_text(json.dumps({"hooks": {"build:common": "make"}}))
    with pytest.raises(formats.PluginFormatError, match="'common' is only allowed"):
        Registry(tmp_path).load_module("k")
