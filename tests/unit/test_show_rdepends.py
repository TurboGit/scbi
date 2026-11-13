"""scbi show --rdepends on YAML plug-ins (the hooks listing a module)."""

from scbi.tools.show import definition_depends_hooks


def test_definition_depends_hooks(tmp_path):
    (tmp_path / "p.yaml").write_text(
        "depends: [m, x]\n"
        "build-depends: {v1: [m], cross: {_: [m], v2: [m]}}\n"
        "tests-depends: [{'if on debian': m}]\n"
        "modules: {common: [m]}\n"
        "config-options: [m]\n")
    found = []
    definition_depends_hooks("m", tmp_path / "p.yaml", found)
    assert sorted(found) == ["p", "p (modules)", "p (test)", "p [cross/v2] (build)", "p [cross] (build)",
                             "p [v1] (build)"]
    found = []
    definition_depends_hooks("x", tmp_path / "p.yaml", found)
    assert found == ["p"]
    (tmp_path / "bad.yaml").write_text("confg: x\n")
    definition_depends_hooks("m", tmp_path / "bad.yaml", found)
    assert found == ["p"]
