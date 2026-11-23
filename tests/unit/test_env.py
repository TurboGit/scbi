

from scbi.bashenv import ShellVars
from scbi.env import Environment


def env(**values) -> Environment:
    return Environment(ShellVars(dict(values), set(values)))


def test_add_prepend_append_remove():
    e = env(V="a:b")
    e.add_to_var("V", "c")
    assert e.get("V") == "c:a:b"
    e.add_to_var("V", "a")  # already there
    assert e.get("V") == "c:a:b"
    e.prepend_to_var("V", "b")
    assert e.get("V") == "b:c:a"
    e.append_to_var("V", "b")
    assert e.get("V") == "c:a:b"
    e.remove_from_var("V", "a")
    assert e.get("V") == "c:b"
    e.remove_from_var("V", "*")
    assert "V" not in e.vars.values
    e.add_to_var("W", "x y")  # unquoted in Bash: first word only
    assert e.get("W") == "x" and "W" in e.vars.exported


def test_empty_values():
    """An empty value does not create the variable nor change it; removing
    the last value unsets it (former driver test142)."""
    e = env()
    e.add_to_var("TLIST", "")
    e.append_to_var("TLIST", "")
    e.prepend_to_var("TLIST", "")
    assert "TLIST" not in e.vars.values
    e = env(TLIST="toto")
    for op in (e.add_to_var, e.append_to_var, e.prepend_to_var):
        op("TLIST", "")
        assert e.get("TLIST") == "toto"
    e.add_to_var("TLIST", "titi")
    assert e.get("TLIST") == "titi:toto"
    e.remove_from_var("TLIST", "toto")
    assert e.get("TLIST") == "titi"
    e.remove_from_var("TLIST", "titi")
    assert "TLIST" not in e.vars.values


def test_path_only_existing_directories(tmp_path):
    e = env(PATH="/usr/bin")
    e.add_to_var("PATH", str(tmp_path / "missing"))
    assert e.get("PATH") == "/usr/bin"
    e.add_to_var("PATH", str(tmp_path))
    assert e.get("PATH") == f"{tmp_path}:/usr/bin"


def test_record(tmp_path):
    rec = tmp_path / "env.cmd"
    e = Environment(record=rec)
    e.set_var("A", "x  y")
    e.unset_var("A")
    assert rec.read_text() == 'define-var SET A "x y"\ndefine-var UNSET A ""\n'
