import random

import pytest

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


def test_system_compiler():
    e = env(PATH="/opt/bin", C_INCLUDE_PATH="/x", OTHER="o")
    e.system_compiler()
    assert e.get("PATH") == "/usr/local/bin:/usr/bin:/bin"
    assert "C_INCLUDE_PATH" not in e.vars.values and e.get("OTHER") == "o"


# ------------------------------------------------------------------ oracle

ACTIONS = ["ADD", "APPEND", "PREPEND", "REMOVE", "SET", "UNSET", "A", "P", "R", "S", "U"]
#  no glob characters, see known_diffs.env_value_has_glob
VALUES = ["a", "b", "c", "a b", "", "/opt/lib", "a:b", "x1", "a  b"]


def sequences(tmp_path, n=150, seed=4):
    rnd = random.Random(seed)
    dirs = [str(tmp_path / "d1"), str(tmp_path / "d2"), str(tmp_path / "missing")]
    (tmp_path / "d1").mkdir(exist_ok=True)
    (tmp_path / "d2").mkdir(exist_ok=True)
    seqs = []
    for _ in range(n):
        ops = []
        for _ in range(rnd.randint(1, 8)):
            var = rnd.choice(["V", "W", "PATH"])
            val = rnd.choice(dirs if var == "PATH" else VALUES)
            ops.append((rnd.choice(ACTIONS), var, val))
        seqs.append(ops)
    return seqs


TEMPLATE = r"""
export V="a:b:x1" W="" PATH="/usr/bin:/bin"
unset W
SCBI_ENV_MODULE=$PWD/env-$BASHPID.cmd
: > $SCBI_ENV_MODULE
eval "$1"
for v in V W PATH; do
  if [[ -v $v ]]; then printf '%s=%s\x1f' $v "${!v}"; else printf '%s\x1f' $v; fi
done
printf '%s' "$(< $SCBI_ENV_MODULE)"
"""


@pytest.mark.oracle
def test_define_var_oracle(oracle, tmp_path):
    seqs = sequences(tmp_path)
    scripts = []
    for ops in seqs:
        scripts.append("\n".join(f'define-var {a} {v} "{val}"' for a, v, val in ops))
    outputs = oracle.batch(TEMPLATE, [(s,) for s in scripts])
    for ops, out in zip(seqs, outputs):
        rec = tmp_path / "env.cmd"
        rec.write_text("")
        e = Environment(ShellVars({"V": "a:b:x1", "PATH": "/usr/bin:/bin"}, {"V", "PATH"}), record=rec)
        for a, v, val in ops:
            e.define_var(a, v, val)
        parts = out.split("\x1f")
        expected = {}
        for p in parts[:3]:
            name, _, value = p.partition("=")
            if "=" in p:
                expected[name] = value
        assert {k: e.vars.values[k] for k in ("V", "W", "PATH") if k in e.vars.values} == expected, ops
        assert rec.read_text().rstrip("\n") == parts[3], ops


COMPILER_VARS = ["PATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH",
                 "LD_LIBRARY_PATH", "ADA_PROJECT_PATH"]


@pytest.mark.oracle
@pytest.mark.parametrize(
    "call, args",
    [
        ("target-env", ("", "")),
        ("target-env", ("/opt/cross", "arm-linux-gnueabi")),
        ("no-target-env", ("", "")),
        ("no-target-env", ("/opt/tc", "")),
        ("system-compiler", ()),
    ],
)
def test_compiler_env_oracle(oracle, call, args):
    import os

    path = os.environ.get("PATH", "/usr/bin:/bin")
    script = f"export PATH={path!r}\n{call} {' '.join(repr(a) for a in args)}\n"
    script += "".join(f'printf "%s\\x1f" "${{{v}}}"\n' for v in COMPILER_VARS)
    expected = oracle.call(script).split("\x1f")[:-1]

    e = env(PATH=path)
    host, bdir = oracle.host, oracle.var("", "SCBI_BDIR")
    if call == "target-env":
        e.target_env(*args, host=host, bdir=bdir)
    elif call == "no-target-env":
        e.no_target_env(*args, host=host, bdir=bdir)
    else:
        e.system_compiler()
    assert [e.get(v) for v in COMPILER_VARS] == expected
