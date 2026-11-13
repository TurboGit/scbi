"""The closure rule of the converter: a Bash plug-in does not inherit a
YAML one (scbi.convert.closure)."""

from scbi.convert import closure


def test_closure(tmp_path):
    (tmp_path / "a").write_text("inherit-plugin b\nfunction a-build() { :; }\n")
    (tmp_path / "b").write_text("inherit-plugin c\nfunction b-build() { :; }\n")
    (tmp_path / "c").write_text("function c-build() { :; }\n")
    (tmp_path / "d").write_text("function d-build() { :; }\n")
    for n in ("b", "c", "d"):
        (tmp_path / f"{n}.yaml").write_text(f"plugin: {n}\n")
    #  a stays Bash: b, then c (inherited by b, now Bash), are Bash again
    assert sorted(closure(tmp_path)) == ["b", "c"]
    assert sorted(p.name for p in tmp_path.glob("*.yaml")) == ["d.yaml"]
