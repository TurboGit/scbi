"""Environment files of the driver: ``.env.yaml`` / ``.env-<name>.yaml``.

An environment file is a YAML file read once when the driver starts. It is
searched, in order, as (``<ename>``: ``env`` or ``env-<name>`` for
``--env=<name>``):

    $PWD/.scbi-<ename>.yaml
    $PWD/../.scbi-<ename>.yaml
    $HOME/.scbi-<ename>.yaml
    $SCBI_PLUGINS/.<ename>.yaml

All its keys are optional::

    inherit: [shared]            # other environment files, read first
    vars:                        # settings, in order
      SCBI_PLAN: ${SCBI_PLAN:-default}
    passthrough: [CC]            # user variables given to the hooks
    functions:                   # hooks and helpers, command language
      define-var: {params: [ACTION, NAME, VALUE], run: apply-var $ACTION $NAME $VALUE}
      rewrite-vcs: {params: [PROXY, OPTIONS, PROTOCOL, URL, DIR], run: ...}
      rewrite-archive: {params: [PROXY, OPTIONS, PROTOCOL, URL, FILE, DIR], run: ...}
      proxy: {params: [NAME], run: export http_proxy=...}
      module-final-step: {run: ...}

- ``inherit``: environment files of the same directory (``shared`` is
  ``.env-shared.yaml`` or ``.scbi-env-shared.yaml``), read first: their
  settings, passthrough variables and functions come before the ones of
  the file, which overrides them.
- ``vars``: the settings, expanded in order as values (``$VAR``,
  ``${VAR:-default}``, ``$(output ...)``...) with the driver variables and
  the previous settings; they become exported driver variables.
- ``functions``: in the command language (scbi.hooks.cmdlang). The ones
  named as the hooks below are called by the driver through adapters
  (:meth:`EnvFile.hook` keeps the interface of the call sites):

  - ``define-var ACTION NAME VALUE``: each environment action of the
    plug-ins; ``apply-var ACTION NAME VALUE`` does the default action (not
    calling it skips the action);
  - ``rewrite-vcs`` / ``rewrite-archive``: the fields of a vcs / archive
    hook as parameters, the output (one field per line) gives the fields
    to use (no output: unchanged);
  - ``proxy NAME``: run with the environment of the VCS or download
    command; the variables it exports are set in it;
  - ``module-final-step``: after each module, with the variables PREFIX
    TARGET VARIANT MODULE FORMODULE MODREF DEPENDS_KIND IS_META
    IS_AGGREGATED IS_UP_TO_DATE and the functions ``env-actions [hook]
    [modref]``, ``module-ref <modref>``, ``module-name <modref>``,
    ``target-dir <module> <variant> [sub]`` (scbi.steps.final).

``SCBI_ENV_DIR`` is the directory of the file.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from scbi.envfile import env_file_name, find_env_file

KEYS = ("inherit", "vars", "passthrough", "functions")
#  function name -> name of the hook of the driver
HOOKS = {"define-var": "define_var", "rewrite-vcs": "rewrite_vcs", "rewrite-archive": "rewrite_archive",
         "proxy": "proxy", "module-final-step": "module_final_step"}
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EnvFileError(Exception):
    """An environment file which cannot be used (message for the user)."""


@dataclass
class EnvFile:
    path: Path | None = None
    settings: dict[str, str] = field(default_factory=dict)
    passthrough: tuple[str, ...] = ()
    #  name -> (params, Function)
    functions: dict[str, object] = field(default_factory=dict)
    hooks: dict[str, Callable] = field(default_factory=dict)
    #  the driver, given by bind() (contexts of the hooks)
    driver: object = None

    def hook(self, name: str) -> Callable | None:
        return self.hooks.get(name)

    def bind(self, driver) -> None:
        """The driver running the hooks (after the settings are set)."""
        self.driver = driver


# ----------------------------------------------------------------- search


def find(name: str, cwd: Path, home: Path, plugins_dir: Path, suffix: str = ".yaml") -> Path | None:
    ename = env_file_name(name)
    for candidate in (
        cwd / f".scbi-{ename}{suffix}",
        cwd / ".." / f".scbi-{ename}{suffix}",
        home / f".scbi-{ename}{suffix}",
        plugins_dir / f".{ename}{suffix}",
    ):
        if candidate.is_file():
            return candidate
    return None


def load(name: str, cwd: Path, home: Path, plugins_dir: Path, variables: dict[str, str]) -> EnvFile:
    """Find and read the environment file ``name`` ("" for the default one).

    A missing default environment is not an error; a missing named one is.
    A Python or Bash environment file without a YAML version is an error.
    """
    path = find(name, cwd, home, plugins_dir)
    if path is None:
        python = find(name, cwd, home, plugins_dir, ".py")
        if python is not None:
            raise EnvFileError(f"build environment {python} is a Python file, environment files are YAML "
                               f"files now: write {python.with_suffix('.yaml').name}")
        bash = find_env_file(name, cwd, home, plugins_dir)
        if bash is not None:
            raise EnvFileError(f"build environment {bash} is a Bash file, convert it with: "
                               f"python3 -m scbi.envconvert {bash}")
        if name:
            raise EnvFileError(f"build environment .{env_file_name(name)} not found")
        return EnvFile()
    env = read(path, variables)
    _make_hooks(env)
    return env


# ------------------------------------------------------------------- read


def _yaml(path: Path) -> dict:
    from scbi.plugin.yamlfmt import _Loader

    try:
        data = yaml.load(path.read_text(), Loader=_Loader) or {}
    except (OSError, yaml.YAMLError) as e:
        raise EnvFileError(f"{path}: {e}") from None
    if not isinstance(data, dict):
        raise EnvFileError(f"{path}: a mapping is expected")
    unknown = [k for k in data if k not in KEYS]
    if unknown:
        raise EnvFileError(f"{path}: unknown key {unknown[0]!r} (keys: {', '.join(KEYS)})")
    return data


def _inherited(path: Path, name: str) -> Path:
    for candidate in (path.parent / f".env-{name}.yaml", path.parent / f".scbi-env-{name}.yaml"):
        if candidate.is_file():
            return candidate
    raise EnvFileError(f"{path}: inherited environment {name!r} not found (.env-{name}.yaml)")


def read(path: Path, variables: dict[str, str], _stack: tuple[Path, ...] = ()) -> EnvFile:
    """The environment file ``path`` with the ones it inherits; the
    settings expanded with ``variables`` (the driver variables)."""
    from scbi.plugin import construct
    from scbi.plugin.construct import DefinitionError

    if path.resolve() in _stack:
        raise EnvFileError(f"{path}: inheritance cycle: {' -> '.join(p.name for p in (*_stack, path))}")
    data = _yaml(path)
    env = EnvFile(path)
    inherit = data.get("inherit") or []
    if isinstance(inherit, str):
        inherit = [inherit]
    for name in inherit:
        base = read(_inherited(path, str(name)), {**variables, **env.settings}, (*_stack, path.resolve()))
        env.settings.update(base.settings)
        env.passthrough += tuple(p for p in base.passthrough if p not in env.passthrough)
        env.functions.update(base.functions)

    values = {**variables, **env.settings, "SCBI_ENV_DIR": str(path.parent)}
    for name, value in (data.get("vars") or {}).items():
        name = str(name)
        if not _NAME.match(name):
            raise EnvFileError(f"{path}: vars: {name!r} is not a variable name")
        value = _expand(path, "" if value is None else str(value), values)
        env.settings[name] = values[name] = value

    passthrough = data.get("passthrough") or []
    if not isinstance(passthrough, list) or not all(isinstance(p, str) for p in passthrough):
        raise EnvFileError(f"{path}: passthrough must be a list of variable names")
    env.passthrough += tuple(p for p in passthrough if p not in env.passthrough)

    for name, f in (data.get("functions") or {}).items():
        f = {"run": f} if isinstance(f, str) else f
        if not isinstance(f, dict) or not isinstance(f.get("run", ""), str):
            raise EnvFileError(f"{path}: functions: {name}: a mapping with params and run is expected")
        try:
            env.functions[str(name)] = construct.function([str(p) for p in f.get("params") or []],
                                                          f.get("run") or "")
        except DefinitionError as e:
            raise EnvFileError(f"{path}: functions: {name}: {e}") from None
    return env


def _expand(path: Path, value: str, values: dict[str, str]) -> str:
    """A setting expanded as a value with ``values``."""
    from scbi.bashenv import ShellVars
    from scbi.env import Environment
    from scbi.hooks.context import HookContext
    from scbi.hooks.expand import ExpandError, expand

    ctx = HookContext(module="", variant="default", hook="env", env=Environment(ShellVars(dict(values), set())),
                      cwd=Path.cwd())
    try:
        return expand(value, ctx)
    except (ExpandError, Exception) as e:  # noqa: BLE001 - reported to the user
        raise EnvFileError(f"{path}: vars: {value}: {e}") from None


# ------------------------------------------------------------------ hooks


def _runner(env: EnvFile, where: str, **kw):
    """A runner of the functions of ``env`` with the context of the
    driver."""
    from scbi.env import Environment
    from scbi.hooks.cmdlang import Runner
    from scbi.hooks.context import HookContext

    d = env.driver
    ctx = HookContext(module="", variant="default", hook="env", env=Environment(d.sv), plan=d.plan,
                      host=d.get("SCBI_HOST"), target=d.get("SCBI_TARGET"), cwd=Path.cwd(),
                      modules_list=[], scbi_bdir=d.get("SCBI_BDIR"))
    for k, v in kw.pop("ctx", {}).items():
        setattr(ctx, k, v)
    functions = {n: (f.params, f.ast) for n, f in env.functions.items()}
    return Runner(ctx, f"{env.path.name}: {where}", functions=functions, **kw)


def _call(env: EnvFile, name: str, args: list[str], out, err=None, environ: dict | None = None,
          variables: dict | None = None, **kw) -> tuple[int, dict]:
    """Run the function ``name`` of the environment file; returns its
    status and its environment (exports)."""
    from scbi.hooks.cmdlang import State

    f = env.functions[name]
    runner = _runner(env, name, **kw)
    state = State(dict(variables or {}), dict(environ if environ is not None else env.driver.sv.environ()),
                  os.getcwd(), out, err or (lambda t: sys.stderr.write(t)))
    for p, v in zip(f.params, args + [""] * len(f.params)):
        state.vars[p] = v
    status = runner.run(f.ast, state)
    return status, state.env


def _make_hooks(env: EnvFile) -> None:
    if "define-var" in env.functions:
        def define_var(uenv, action, name, value):
            _call(env, "define-var", [action, name, value], out=lambda t: None,
                  apply_var=lambda a, n, v: uenv.apply(a, n, v))
        env.hooks["define_var"] = define_var

    for fname in ("rewrite-vcs", "rewrite-archive"):
        if fname in env.functions:
            def rewrite(record, fname=fname):
                chunks: list[str] = []
                _call(env, fname, list(record), out=chunks.append)
                lines = "".join(chunks).split("\n")
                if lines and lines[-1] == "":
                    lines.pop()
                return lines or list(record)
            env.hooks[HOOKS[fname]] = rewrite

    if "proxy" in env.functions:
        def proxy(name, environ):
            _, new = _call(env, "proxy", [name], out=lambda t: sys.stdout.write(t), environ=environ)
            for k in [k for k in environ if k not in new]:
                del environ[k]
            environ.update(new)
        env.hooks["proxy"] = proxy

    if "module-final-step" in env.functions:
        def module_final_step(ctx):
            extra = {
                "env-actions": lambda a: [x for t in ctx.env_actions(*(a[:1] or ["env"]), *(a[1:2] or []))
                                          for x in t],
                "module-ref": lambda a: list(ctx.module_ref(*(a[:1] or [""]), *(a[1:2] or []))),
                "module-name": lambda a: ctx.module_name(a[0] if a else ""),
                "target-dir": lambda a: ctx.target_dir(*(a + ["", "", ""])[:3]),
            }
            variables = {"PREFIX": ctx.prefix, "TARGET": ctx.target, "VARIANT": ctx.variant,
                         "MODULE": ctx.module, "FORMODULE": ctx.formodule, "MODREF": ctx.modref,
                         "DEPENDS_KIND": ctx.depends_kind, "IS_META": ctx.is_meta,
                         "IS_AGGREGATED": ctx.is_aggregated, "IS_UP_TO_DATE": ctx.is_up_to_date}
            status, _ = _call(env, "module-final-step", [], out=lambda t: sys.stdout.write(t),
                              variables=variables, extra=extra,
                              ctx={"module": ctx.module, "variant": ctx.variant},
                              #  log LEVEL MESSAGE: a driver message for the module
                              log=lambda level, msg: env.driver.log.ilog_raw(ctx.module, "  " * level + msg))
            if status != 0:
                raise RuntimeError(f"module-final-step failed with status {status}")
        env.hooks["module_final_step"] = module_final_step
