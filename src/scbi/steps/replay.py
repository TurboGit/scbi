"""Reproduction of an interpreted command hook: the replay file
``$TVDIR/logs/<step>.cmd`` written by the step wrapper and read by
``scbi replay FILE [--trace]``.

The file is YAML, readable and editable: the directory, the environment
of the hook, its parameters, the plug-in variables, the driver
variables the built-ins read (SCBI_*), the config-options of the module,
the hook body (``run``) and the plug-in functions it may call.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from scbi.bashenv import ShellVars
from scbi.env import Environment
from scbi.hooks.cmdlang import Runner, State, parse
from scbi.hooks.context import HookContext
from scbi.plan import PlanState

VERSION = 1


@dataclass
class Replay:
    module: str
    variant: str
    hook: str
    function: str  # the hook function name (<module>[-<variant>]-<hook>)
    plugin_file: str
    cwd: str
    host: str
    target: str
    run: str  # the hook body (command language)
    line: int = 1  # line of the body in the plug-in file
    params: dict[str, str] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)  # plug-in vars
    driver: dict[str, str] = field(default_factory=dict)  # SCBI_* of the driver
    environment: dict[str, str] = field(default_factory=dict)
    config_options: list[str] = field(default_factory=list)
    functions: dict[str, dict] = field(default_factory=dict)  # name -> {params, run}
    version: str = ""  # get-version


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str)


def write(path: str, r: Replay) -> None:
    data = {"replay": VERSION, "module": r.module, "variant": r.variant, "hook": r.hook,
            "function": r.function, "plugin-file": r.plugin_file, "line": r.line,
            "cwd": r.cwd, "host": r.host, "target": r.target, "version": r.version,
            "params": r.params, "variables": r.variables, "config-options": r.config_options,
            "run": r.run if r.run.endswith("\n") else r.run + "\n",
            "functions": r.functions, "driver": r.driver, "environment": r.environment}
    with open(path, "w") as f:
        f.write(f"# scbi replay {path}\n")
        yaml.dump(data, f, Dumper=_Dumper, sort_keys=False, default_flow_style=False, allow_unicode=True)


def load(path: str) -> Replay:
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or data.get("replay") != VERSION:
        raise ValueError(f"{path}: not a replay file")
    return Replay(
        module=data["module"], variant=data["variant"], hook=data["hook"], function=data["function"],
        plugin_file=data.get("plugin-file", ""), cwd=data["cwd"], host=data["host"], target=data["target"],
        run=data.get("run") or "", line=int(data.get("line") or 1),
        params={k: str(v) for k, v in (data.get("params") or {}).items()},
        variables={k: _value(v) for k, v in (data.get("variables") or {}).items()},
        driver={k: str(v) for k, v in (data.get("driver") or {}).items()},
        environment={k: str(v) for k, v in (data.get("environment") or {}).items()},
        config_options=[str(x) for x in data.get("config-options") or []],
        functions=data.get("functions") or {}, version=str(data.get("version") or ""),
    )


def _value(v):
    return [str(x) for x in v] if isinstance(v, list) else str(v)


def context(r: Replay) -> HookContext:
    values = {**r.driver, **r.environment}
    plan = PlanState()
    if r.version:
        plan.modver[r.module] = f"{r.module}/{r.variant}:{r.version}"
    return HookContext(module=r.module, variant=r.variant, hook=r.hook, params=dict(r.params),
                       env=Environment(ShellVars(values, set(r.environment))), plan=plan,
                       host=r.host, target=r.target, cwd=Path(r.cwd))


def runner(r: Replay, ctx: HookContext, trace=None) -> Runner:
    funcs = {name: (tuple(f.get("params") or ()), parse(f.get("run") or "", int(f.get("line") or 1)))
             for name, f in r.functions.items()}
    return Runner(ctx, f"{Path(r.plugin_file).name}: {r.hook}", config_options=lambda: list(r.config_options),
                  functions=funcs, trace=trace)


def replay(path: str, trace: bool = False) -> int:
    """Run the hook of a replay file, its output to the console."""
    r = load(path)
    ctx = context(r)

    def out(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    state = State(dict(r.variables), dict(r.environment), r.cwd, out, out)
    run = runner(r, ctx, (lambda line: out(line + "\n")) if trace else None)
    return run.run(parse(r.run, r.line), state)
