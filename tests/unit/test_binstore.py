"""The binary store: keys (normalization) and relocation."""

import os

import pytest

from scbi.binstore import key, relocate


class FakeDriver:
    def __init__(self, **values):
        self.values = values

    def get(self, name):
        return self.values.get(name, "")


def _env(bdir):
    return {"PATH": "/usr/bin", "C_INCLUDE_PATH": f"{bdir}/lib1/x86_64-linux-gnu-default/install/include",
            "SCBI_BDIR": bdir, "SCBI_JOBS": "8", "SCBI_RUN_ID": "r1", "CFLAGS": "-O2"}


def test_normalize_sandbox_and_home():
    roots = [("/home/a/sbx", "<bdir>"), ("/home/a", "<home>")]
    assert key.normalize("/home/a/sbx/lib1/include:/home/a/.local/bin", roots) == "<bdir>/lib1/include:<home>/.local/bin"
    #  /home/a/sbx2 is not in the sandbox /home/a/sbx
    assert key.normalize("/home/a/sbx2/x", roots) == "<home>/sbx2/x"


def test_same_key_in_two_sandboxes(tmp_path):
    keys = []
    for name in ("a", "b"):
        bdir = str(tmp_path / name)
        d = FakeDriver(SCBI_BDIR=bdir, HOME="/home/u", SCBI_JOBS="8" if name == "a" else "2")
        comps = key.components(d, "bid", {"lib1": "k1"}, _env(bdir))
        keys.append(key.keys(d, comps))
    #  the relocatable keys are the same, the bound ones differ
    assert keys[0][0] == keys[1][0]
    assert keys[0][1] != keys[1][1]


@pytest.mark.parametrize("change", [
    {"CFLAGS": "-O3"},                      # the environment
    {"depends": {"lib1": "k2"}},            # a dependency
])
def test_key_changes(tmp_path, change):
    d = FakeDriver(SCBI_BDIR=str(tmp_path), HOME="/home/u")
    env = _env(str(tmp_path))
    base = key.keys(d, key.components(d, "bid", {"lib1": "k1"}, env))[0]
    deps = change.pop("depends", {"lib1": "k1"})
    env.update(change)
    assert key.keys(d, key.components(d, "bid", deps, env))[0] != base


def test_ignored_variables(tmp_path):
    env = _env(str(tmp_path))
    d = FakeDriver(SCBI_BDIR=str(tmp_path), SCBI_BINARY_KEY_IGNORE="CFLAGS")
    base = key.keys(d, key.components(d, "bid", {}, env))[0]
    env["CFLAGS"] = "-O3"
    assert key.keys(d, key.components(d, "bid", {}, env))[0] == base


def _tree(tmp_path, origin):
    tree = tmp_path / "install"
    (tree / "lib" / "pkgconfig").mkdir(parents=True)
    (tree / "lib" / "pkgconfig" / "x.pc").write_text(f"prefix={origin}/x/install\nother={origin}2/y\n")
    (tree / "lib" / "libx.so.1").write_bytes(b"\x7fELF\0" + f"{origin}/x/install/lib".encode() + b"\0end\0")
    os.symlink(f"{origin}/x/install/lib/libx.so.1", tree / "lib" / "libx.so")
    (tree / "lib" / "__pycache__").mkdir()
    (tree / "lib" / "__pycache__" / "m.pyc").write_bytes(b"\0" + origin.encode())
    return str(tree)


def test_scan_and_relocate_shorter(tmp_path):
    tree = _tree(tmp_path, "/home/alice/sbx")
    files = relocate.scan(tree, ["/home/alice/sbx"])
    assert {f["path"]: f["kind"] for f in files} == {
        "lib/libx.so": "link", "lib/libx.so.1": "binary", "lib/pkgconfig/x.pc": "text"}
    assert relocate.relocatable(files)
    mapping = [("/home/alice/sbx", "/b/s")]
    relocate.relocate(tree, files, mapping)
    assert relocate.remaining(tree, files, mapping) == []
    assert open(os.path.join(tree, "lib/pkgconfig/x.pc")).read() == \
        "prefix=/b/s/x/install\nother=/home/alice/sbx2/y\n"
    data = open(os.path.join(tree, "lib/libx.so.1"), "rb").read()
    #  same size, the C string padded, the next string unchanged
    assert len(data) == len(b"\x7fELF\0/home/alice/sbx/x/install/lib\0end\0")
    assert data.startswith(b"\x7fELF\0/b/s/x/install/lib\0") and data.endswith(b"\0end\0")
    assert os.readlink(os.path.join(tree, "lib/libx.so")) == "/b/s/x/install/lib/libx.so.1"


def test_relocate_longer_binary(tmp_path):
    tree = _tree(tmp_path, "/s")
    files = relocate.scan(tree, ["/s"])
    with pytest.raises(relocate.RelocationError):
        relocate.relocate(tree, files, [("/s", "/a/much/longer/sandbox")])


def test_not_relocatable(tmp_path):
    tree = tmp_path / "install"
    tree.mkdir()
    #  the path is not in a C string (no NUL after it)
    (tree / "data.bin").write_bytes(b"\0\0/home/a/sbx/x")
    files = relocate.scan(str(tree), ["/home/a/sbx"])
    assert files == [{"path": "data.bin", "kind": "other"}]
    assert not relocate.relocatable(files)


def test_env_file_binary_stores(tmp_path):
    from pathlib import Path

    from scbi import envyaml

    path = Path(tmp_path / ".env.yaml")
    assert envyaml._binary_stores(path, ["file://$H/a", {"url": "https://x/s", "mode": "ro"}], {"H": "/h"}) == [
        ("file:///h/a", "rw"), ("https://x/s", "ro")]
    for bad in ("file:///a", [{"url": "x", "mode": "rx"}], [{"mode": "ro"}]):
        with pytest.raises(envyaml.EnvFileError):
            envyaml._binary_stores(path, bad, {})
