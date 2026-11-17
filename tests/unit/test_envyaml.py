"""YAML environment files (scbi.envyaml) and the converter of the Bash
ones (scbi.envconvert)."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from scbi import envconvert, envyaml
from scbi.bashenv import ShellVars
from scbi.plan import PlanState


def dirs(tmp_path):
    cwd, home, plugins = tmp_path / "w", tmp_path / "h", tmp_path / "p"
    for d in (cwd, home, plugins):
        d.mkdir()
    return cwd, home, plugins


def test_search_order_and_missing(tmp_path):
    cwd, home, plugins = dirs(tmp_path)
    assert envyaml.load("", cwd, home, plugins, {}).path is None  # no default env: fine
    with pytest.raises(envyaml.EnvFileError, match=r"\.env-x not found"):
        envyaml.load("x", cwd, home, plugins, {})
    (plugins / ".env-x").write_text("A=1\n")
    with pytest.raises(envyaml.EnvFileError, match="is a Bash file, convert it with: python3 -m scbi.envconvert"):
        envyaml.load("x", cwd, home, plugins, {})
    (plugins / ".env-x.py").write_text("A = 'py'\n")
    with pytest.raises(envyaml.EnvFileError, match="is a Python file, environment files are YAML"):
        envyaml.load("x", cwd, home, plugins, {})
    (plugins / ".env-x.yaml").write_text("vars: {A: plugins}\n")
    assert envyaml.load("x", cwd, home, plugins, {}).settings == {"A": "plugins"}
    (home / ".scbi-env-x.yaml").write_text("vars: {A: home}\n")
    assert envyaml.load("x", cwd, home, plugins, {}).settings == {"A": "home"}
    (cwd / ".scbi-env-x.yaml").write_text("vars: {A: cwd}\n")
    assert envyaml.load("x", cwd, home, plugins, {}).settings == {"A": "cwd"}


def test_vars_inherit_and_errors(tmp_path):
    (tmp_path / ".env-base.yaml").write_text(
        "vars:\n  SCBI_PLAN: base\n  B: from-base\npassthrough: [CC]\n"
        "functions:\n  helper: {params: [X], run: echo $X}\n")
    path = tmp_path / ".env.yaml"
    path.write_text("""
inherit: [base]
vars:
  SCBI_PLAN: ${SCBI_PLAN:-default}-$B
  SCBI_JOBS: ${SCBI_JOBS:-4}
  ROOT: $SCBI_ENV_DIR/root
  ON: yes
  V: $(output echo hello)
passthrough: [LD]
""")
    env = envyaml.read(path, {"SCBI_JOBS": "8"})
    #  inherited first, overridden; expanded in order
    assert env.settings == {"SCBI_PLAN": "base-from-base", "B": "from-base", "SCBI_JOBS": "8",
                            "ROOT": f"{tmp_path}/root", "ON": "yes", "V": "hello"}
    assert env.passthrough == ("CC", "LD") and set(env.functions) == {"helper"}
    path.write_text("unknown: 1\n")
    with pytest.raises(envyaml.EnvFileError, match="unknown key 'unknown'"):
        envyaml.read(path, {})
    path.write_text("inherit: [self]\n")
    (tmp_path / ".env-self.yaml").write_text("inherit: [self]\n")
    with pytest.raises(envyaml.EnvFileError, match="inheritance cycle"):
        envyaml.read(path, {})
    path.write_text("functions:\n  f: {run: 'if :'}\n")
    with pytest.raises(envyaml.EnvFileError, match="functions: f"):
        envyaml.read(path, {})


def env_with(tmp_path, text):
    path = tmp_path / ".env.yaml"
    path.write_text(text)
    env = envyaml.read(path, {})
    envyaml._make_hooks(env)
    env.bind(SimpleNamespace(sv=ShellVars({"PATH": os.environ["PATH"], "TESTREPOS": "/repos"}, {"PATH"}),
                             plan=PlanState({}), get=lambda n: ""))
    return env


def test_hooks(tmp_path, capfd):
    env = env_with(tmp_path, r"""
functions:
  define-var:
    params: [ACTION, NAME, VALUE]
    run: |-
      if $NAME == LD_LIBRARY_PATH:
          return
      apply-var $ACTION $NAME ${VALUE/\/usr\/local//opt/local}
  rewrite-vcs:
    params: [PROXY, OPTIONS, PROTOCOL, URL]
    run: |-
      echo $PROXY
      echo $OPTIONS
      echo $PROTOCOL
      echo ${URL/\/old/$TESTREPOS}
  proxy:
    params: [NAME]
    run: |-
      if $NAME == corp:
          export http_proxy=http://proxy:3128
  module-final-step:
    run: |-
      for A V X in $(env-actions):
          echo "$MODULE $A $V=$X"
""")
    applied = []
    uenv = SimpleNamespace(apply=lambda a, n, v: applied.append((a, n, v)))
    env.hook("define_var")(uenv, "ADD", "PATH", "/usr/local/bin")
    env.hook("define_var")(uenv, "SET", "LD_LIBRARY_PATH", "/x")
    assert applied == [("ADD", "PATH", "/opt/local/bin")]
    assert env.hook("rewrite_vcs")(["none", "none", "git", "/old/lib"]) == ["none", "none", "git", "/repos/lib"]
    environ = {"A": "1"}
    env.hook("proxy")("corp", environ)
    assert environ == {"A": "1", "http_proxy": "http://proxy:3128"}
    ctx = SimpleNamespace(prefix="/p", target="t", variant="default", module="m", formodule="@root",
                          modref="m", depends_kind="default", is_meta="no", is_aggregated="no",
                          is_up_to_date="no", env_actions=lambda hook="env", modref=None: [("ADD", "PATH", "/p/bin")])
    env.hook("module_final_step")(ctx)
    assert capfd.readouterr().out == "m ADD PATH=/p/bin\n"


def test_convert(tmp_path):
    text, issues = envconvert.convert_text(
        "\n[[ -f ${SCBI_ENV_DIR}/.env-shared ]] &&\n    source ${SCBI_ENV_DIR}/.env-shared\n\n"
        "# comment\nSCBI_PLAN=${SCBI_PLAN:-default}\nexport A=\"x $B/y\"\nV='a b'\nP=$(python3 -V)\n")
    assert issues == []
    assert text.split("\n")[2:] == ["inherit: [shared]", "", "vars:", "  # comment",
                                    "  SCBI_PLAN: ${SCBI_PLAN:-default}", "  A: x $B/y", "  V: a b",
                                    "  P: $(output python3 -V)", ""]
    #  the result loads
    (tmp_path / ".env-shared.yaml").write_text("vars: {S: 1}\n")
    path = tmp_path / ".env.yaml"
    path.write_text(text.replace("$(output python3 -V)", "p"))
    assert envyaml.read(path, {"B": "/b"}).settings == {"S": "1", "SCBI_PLAN": "default", "A": "x /b/y",
                                                       "V": "a b", "P": "p"}
    _, issues = envconvert.convert_text("function module-final-step()\n{\n    echo $1\n}\n"
                                        "C=$(a | b)\nls\n")
    assert [i.split(":")[0] for i in issues] == ["line 1", "line 5", "line 6"]


def test_repository_env():
    root = Path(__file__).resolve().parents[2]
    env = envyaml.read(root / "scripts.d" / ".env.yaml", {})
    assert env.settings == {"SCBI_PLAN": "default", "SCBI_CLANG_VERSION": "16", "SCBI_GTK_VERSION": "3.0"}
