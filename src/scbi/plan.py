"""Build plans.

Port of the plan handling of scripts.d/9_versions (``load-module-plan``,
``register-module-plan``, ``_internal_merge_variant``, ``check-barrier``,
``has-discriminant``) and of ``get-module-ref`` (scripts.d/0_runtime).

The state is the same as the Bash global variables:

- ``modver``       SCBI_MODVER       module (or ``for=module``) -> module ref,
                                     plus ``<module>.skip`` / ``.keep`` flags
- ``plan_hist``    SCBI_PLAN_HIST    module -> ";plan,ref;plan,ref..."
- ``plan_loaded``  SCBI_PLAN_LOADED  plan names already loaded
- ``module_alias`` SCBI_MODULE_ALIAS plug-in -> alternate plug-in

The code follows the Bash implementation closely, including its word
splitting of unquoted expansions, since the resulting plan must be identical
(checked by the oracle tests in tests/unit/test_plan.py).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from scbi.bashcompat import assoc_keys, read_fields, read_lines, words
from scbi.modref import has_variant, parse_module_ref


class PlanError(Exception):
    """Plan error, reported in Bash with ``elog build <message>`` + exit 1."""

    def __init__(self, message: str, module: str = "build"):
        super().__init__(message)
        self.module = module
        self.message = message


def check_barrier(variant: str, discs: str, discriminants: Iterable[str]) -> bool:
    """Port of ``check-barrier``: all discriminants/variants must match."""
    discriminants = set(discriminants)
    for d in words(discs.replace(",", " ")):
        if not (d in discriminants or has_variant(variant, d)):
            return False
    return True


def merge_variant(cvariant: str, rvariant: str) -> str:
    """Port of ``_internal_merge_variant``.

    Merge the variant of a module in a group (``cvariant``) with the group
    variant (``rvariant``) which may add (``+v``) or remove (``-v``)
    variants. Returns ``/<variants>`` or the empty string.
    """
    rvariant = rvariant.replace("+", " +").replace("-", " -").replace(".", " .")

    ref = "" if cvariant == "default" else cvariant
    aref = ""
    dref: list[str] = []
    action = "no"

    def append(cur: str, value: str) -> str:
        return f"{cur}.{value}" if cur else value

    for v in words(rvariant):
        if v[:1] == "+":
            action = "add"
            aref = append(aref, v[1:])
        elif v[:1] == "-":
            action = "del"
            dref += words(v[1:])
        elif action == "add":
            aref = append(aref, v[1:])
        elif action == "del":
            dref += words(v[1:])
        else:
            ref = ""
            aref = append(aref, v.replace(".", "", 1))

    #  Add current variant (if any) after group variants
    nref = aref
    for o in words(ref.replace(".", " ")):
        if not has_variant(nref, o):
            nref = append(nref, o)
    ref = nref

    #  Remove variants if needed
    for n in dref:
        if ref.startswith(f"{n}."):
            ref = ref[len(n) + 1 :]
        if ref.endswith(f".{n}"):
            ref = ref[: -len(n) - 1]
        ref = ref.replace(f".{n}.", ".")
        if ref == n:
            ref = ""

    return f"/{ref}" if ref else ""


def _bash_regex_groups(pattern: str, value: str) -> tuple[str, str] | None:
    """``[[ $value =~ $pattern ]]`` and BASH_REMATCH[1], BASH_REMATCH[2].

    Bash uses POSIX extended regular expressions; Python ``re`` is used as
    an approximation (identical for the patterns used in plans).
    """
    try:
        m = re.search(pattern, value)
    except re.error:
        return None
    if m is None:
        return None

    def group(i: int) -> str:
        if i > (m.re.groups or 0):
            return ""
        return m.group(i) or ""

    return group(1), group(2)


IsBuilt = Callable[[str, str], bool]


@dataclass
class PlanState:
    modver: dict[str, str] = field(default_factory=dict)
    plan_hist: dict[str, str] = field(default_factory=dict)
    plan_loaded: dict[str, str] = field(default_factory=dict)
    module_alias: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------ registering

    def register(self, args: list[str], is_built: IsBuilt) -> None:
        """Port of ``register-module-plan FROM MOD REF KIND``.

        ``args`` are the words passed to the Bash function (the callers use
        unquoted expansions, so arguments may shift when one is empty).
        """
        frm, mod, ref, kind = (args + ["", "", "", ""])[:4]

        if kind == "skip":
            self.modver[f"{mod}.skip"] = "yes"
            if not self.modver.get(mod):
                self.modver[mod] = mod
        elif kind == "force":
            self.modver.pop(f"{mod}.skip", None)
            if not self.modver.get(mod):
                self.modver[mod] = mod
        elif kind == "keep":
            mref = self.modver.get(mod, "")
            #  Keep module only if already built
            if mref:
                m = parse_module_ref(mref)
                if is_built(m.module, m.variant):
                    self.modver[f"{mod}.keep"] = "yes"
        else:
            self.modver[mod] = ref

        self.plan_hist[mod] = self.plan_hist.get(mod, "") + f";{frm},{ref}"

    # ------------------------------------------------------------- reference

    def module_ref(self, modref: str, for_module: str = "@root") -> list[str]:
        """Port of ``get-module-ref``: (module, variant, kind, version).

        Returned as the Bash array (unquoted fields: empty ones dropped).
        """
        for_module = re.sub(r":.*", "", for_module, count=1, flags=re.S)
        for_module = re.sub(r"/.*", "", for_module, count=1, flags=re.S)

        info = (parse_module_ref(modref).to_bash_array() + [""] * 4)[:4]
        module = info[0]
        fmodule = f"{for_module}={module}"

        modplan = self.modver.get(fmodule, "")
        if not modplan:
            modplan = self.modver.get(module, "")
            if modplan:
                info = (parse_module_ref(modplan).to_bash_array() + [""] * 4)[:4]
        else:
            info = (parse_module_ref(modplan).to_bash_array() + [""] * 4)[:4]
            module = fmodule

        if self.modver.get(f"{module}.skip") == "yes":
            info[3] = "skip"
        elif self.modver.get(f"{module}.keep") == "yes":
            info[3] = f"keep:{info[3]}"

        return words(" ".join(info))


class PlanLoader:
    """Load build plans into a :class:`PlanState` (``load-module-plan``)."""

    def __init__(
        self,
        state: PlanState,
        plugins_dir: Path,
        discriminants: Iterable[str] = (),
        cwd: Path | None = None,
        is_built: IsBuilt | None = None,
    ):
        self.state = state
        self.plugins_dir = Path(plugins_dir)
        self.discriminants = set(discriminants)
        self.cwd = Path(cwd) if cwd is not None else Path(os.getcwd())
        self.is_built = is_built or (lambda module, variant: False)

    def plan_file(self, name: str) -> Path:
        local = self.cwd / f".scbi-plan-{name}"
        if local.is_file():
            return local
        return self.plugins_dir / f".plan-{name}"

    # ------------------------------------------------------------------ load

    def load(self, nameref: str) -> None:
        state = self.state

        if "/" not in nameref:
            variant = ""
            name = nameref
        else:
            variant = nameref.split("/", 1)[1]
            name = nameref.rsplit("/", 1)[0]

        #  Load a plan only once
        if state.plan_loaded.get(name) == "yes":
            return
        state.plan_loaded[name] = "yes"

        sets: dict[str, str] = {}

        def resolve_set(ref: str) -> list[str]:
            if sets and "$" in ref:
                for var in assoc_keys(sets):
                    val = sets[var]
                    ref = ref.replace("${" + var + "}", val, 1)
                    ref = ref.replace("$" + var, val, 1)
            #  echo $REF, then used unquoted by the caller
            return words(ref)

        def register(*parts: str | list[str]) -> None:
            args: list[str] = []
            for p in parts:
                args += p if isinstance(p, list) else words(p)
            state.register(args, self.is_built)

        def barrier(discs: str) -> bool:
            return check_barrier(variant, discs, self.discriminants)

        def resolve_as(plg1: str, plg2: str, vrex: str) -> str:
            module = (parse_module_ref(plg1).to_bash_array() + [""])[0]

            asr = state.modver.get(plg2, "")
            skp = state.modver.get(f"{plg2}.skip", "")
            if not asr:
                raise PlanError(f"{plg2} has no reference in build plan")

            ainfo = (parse_module_ref(asr).to_bash_array() + [""] * 4)[:4]
            var, knd, ref = ainfo[1], ainfo[2], ainfo[3]
            a = ""

            vsuffix = ""
            vprefix = vrex.split("/", 1)[0]
            if vprefix == vrex:
                vprefix = ""
            else:
                vsuffix = vrex.rsplit("/", 1)[1]
                vrex = vrex.split("/", 1)[1]
                vrex = vrex.rsplit("/", 1)[0] if "/" in vrex else vrex

            if vrex:
                groups = _bash_regex_groups(vrex, ref)
                if groups is not None:
                    ref = f"{vprefix}{groups[0]}{groups[1]}{vsuffix}"

            if skp == "yes":
                ref = "skip"
            if knd == "VERSION":
                a = "#"

            res = module
            if var != "default":
                res += f"/{var}"
            if ref != "NONE":
                res += f":{a}{ref}"
            return res

        plan = self.plan_file(name)
        if not plan.is_file():
            raise PlanError(f"build plan .plan-{nameref} does not exists")

        group = "no"
        gmod: list[str] = []

        for line in read_lines(plan.read_text()):
            modref, arg1, arg2, arg3, arg4, arg5 = read_fields(line, 6)

            if modref.startswith("#"):
                continue

            elif modref == "@load":
                self.load(arg1)

            elif modref == "@on":
                if arg2 != "use":
                    raise PlanError("syntax error, missing use in @on")
                if barrier(arg1):
                    info = parse_module_ref(arg3).to_bash_array() + [""] * 4
                    module, version = info[0], info[3]
                    register(name, module, resolve_set(re.sub(r"^.*=", "", arg3, flags=re.S)), version)

            elif modref == "@alias":
                if arg2 != "use":
                    raise PlanError("syntax error, missing use in @alias")
                state.module_alias[arg1] = arg3

            elif modref == "@for":
                if arg2 != "use":
                    raise PlanError("syntax error, missing use in @for")
                info = parse_module_ref(f"{arg1}={arg3}").to_bash_array() + [""] * 4
                module, version = info[0], info[3]
                register(name, module, resolve_set(arg3), version)

            elif modref == "@ref" and group == "no":
                if arg2 != "as":
                    raise PlanError(f"syntax error, unknown option {arg2} in @ref")
                if arg4 != "" and arg4 != "version":
                    raise PlanError(f"syntax error, unknown option {arg4} in @ref")

                mref = resolve_as(arg1, arg3, arg5)
                info = parse_module_ref(arg1).to_bash_array() + [""] * 4
                module, ref = info[0], info[3]
                register(name, module, resolve_set(mref), ref)

            elif modref == "@set":
                if arg2 != "=":
                    raise PlanError('syntax error, missing "=" in @set')
                sets[arg1] = arg3

            elif modref == "":
                pass

            elif modref.startswith("]"):
                gref = arg1 if arg1 else modref[1:]

                #  set REF to all module's group in GMOD
                for mod in words(" ".join(gmod)):
                    info = parse_module_ref(mod).to_bash_array() + [""] * 4
                    module, mvariant, kind, version = info[:4]

                    #  If version is inherit then just take the
                    #  current recorded version for this module.
                    if version == "NONE" and mvariant == "default" and state.modver.get(module):
                        info = parse_module_ref(state.modver[module]).to_bash_array() + [""] * 4
                        module, mvariant, kind, version = info[:4]

                    rinfo = parse_module_ref(f"name{gref}").to_bash_array() + [""] * 4
                    rvariant, rkind, rversion = rinfo[1], rinfo[2], rinfo[3]

                    fref = ""

                    #  Override the variant & version only if defined in REF
                    if rvariant != "default":
                        fref = merge_variant(mvariant, rvariant)
                    elif mvariant != "default":
                        fref = f"/{mvariant}"

                    if rversion != "NONE":
                        fref += f":#{rversion}" if rkind == "VERSION" else f":{rversion}"
                    elif version != "NONE":
                        fref += f":#{version}" if kind == "VERSION" else f":{version}"

                    register(name, module, resolve_set(f"{module}{fref}"), rversion)

                group = "no"
                gmod = []

            elif group != "no":
                #  store all module's group in GMOD
                if modref == "@ref" and arg2 == "as" and group == "yes":
                    if arg4 != "" and arg4 != "version":
                        raise PlanError(f"syntax error, unknown option {arg4} in @ref")
                    modref = resolve_as(arg1, arg3, arg5)

                if group == "yes":
                    gmod.append(modref)

            elif modref == "[":
                if arg1:
                    #  Up to three alternative barriers; the first one is
                    #  always checked (an empty barrier is true).
                    alternatives = [arg2] + [d for d in (arg3, arg4) if d]
                    matched = any(barrier(d) for d in alternatives)
                    if arg1 == "=":
                        group = "yes" if matched else "closed"
                    elif arg1 == "/=":
                        group = "closed" if matched else "yes"
                    else:
                        raise PlanError(f"build plan unexpected {arg1} on group start")
                else:
                    group = "yes"

            else:
                info = parse_module_ref(modref).to_bash_array() + [""] * 4
                module, ref = info[0], info[3]
                register(name, module, resolve_set(re.sub(r"^.*=", "", modref, flags=re.S)), ref)

        if group == "yes":
            raise PlanError(f"build plan group is not closed .plan-{nameref}")
