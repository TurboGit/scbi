from __future__ import annotations

import re
from pathlib import Path
from .models import Plan, PlanEntry, PlanError, PlanSyntaxError, PlanNotFoundError, ModuleRef, RefKind


class PlanReader:
    def __init__(
        self,
        plugins_dir: str | Path,
        discriminants: set[str] | None = None,
    ):
        self.plugins_dir = Path(plugins_dir)
        self.discriminants = discriminants or set()

        self._variables: dict[str, str] = {}
        self._plan: Plan | None = None
        self._loaded_plans: set[str] = set()

        # Group state
        self._group_state: str = "no"
        self._group_modules: list[tuple[str, str]] = []

    def load(self, plan_name: str) -> Plan:
        self._plan = Plan(name=plan_name)
        self._variables = {}
        self._loaded_plans = set()
        self._group_state = "no"
        self._group_modules = []

        self._load_plan_file(plan_name, source=plan_name)
        return self._plan

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _load_plan_file(self, name: str, source: str) -> None:
        if name in self._loaded_plans:
            return
        self._loaded_plans.add(name)

        candidates = [
            self.plugins_dir / f".plan-{name}",
            Path.cwd() / f".plan-{name}",
        ]
        plan_file: Path | None = None
        for p in candidates:
            if p.exists():
                plan_file = p
                break

        if plan_file is None:
            raise PlanNotFoundError(f"plan .plan-{name} not found in {self.plugins_dir}")

        with plan_file.open() as f:
            for line in f:
                self._process_line(line.rstrip(), source=name)

        if self._group_state == "yes":
            raise PlanSyntaxError(
                f"build plan group is not closed in .plan-{name}"
            )

    # ------------------------------------------------------------------
    # Line processing
    # ------------------------------------------------------------------

    _SET_RE = re.compile(r"@set\s+")
    _COMMENT_RE = re.compile(r"^\s*#")

    def _process_line(self, line: str, source: str) -> None:
        stripped = line.strip()

        if not stripped:
            return

        if self._COMMENT_RE.match(stripped):
            return

        modref = stripped
        rest = ""

        parts = stripped.split(None, 4)
        modref = parts[0]
        arg1 = parts[1] if len(parts) > 1 else ""
        arg2 = parts[2] if len(parts) > 2 else ""
        arg3 = parts[3] if len(parts) > 3 else ""
        arg4 = parts[4] if len(parts) > 4 else ""

        if modref == "@load":
            self._handle_load(arg1, source)
        elif modref == "@on":
            self._handle_on(arg1, arg2, arg3, source)
        elif modref == "@alias":
            self._handle_alias(arg1, arg2, arg3)
        elif modref == "@for":
            self._handle_for(arg1, arg2, arg3, source)
        elif modref == "@ref" and self._group_state == "no":
            self._handle_ref(arg1, arg2, arg3, source)
        elif modref == "@set":
            self._handle_set(arg1, arg2, arg3)
        elif modref.startswith("]"):
            self._handle_group_close(modref, arg1, source)
        elif self._group_state != "no":
            self._handle_group_member(stripped, source)
        elif modref == "[" or modref.startswith("["):
            self._handle_group_open(modref, arg1, arg2, arg3, arg4, source)
        else:
            self._handle_module_ref(stripped, source)

    # ------------------------------------------------------------------
    # Directives
    # ------------------------------------------------------------------

    def _handle_load(self, plan_name: str, source: str) -> None:
        if plan_name:
            self._load_plan_file(plan_name, source=plan_name)

    def _handle_on(self, disc: str, use: str, modref: str, source: str) -> None:
        if use != "use":
            raise PlanSyntaxError("syntax error, missing use in @on")
        if self._check_barrier("", disc):
            resolved = self._resolve_variables(modref)
            m = ModuleRef.parse(resolved)
            self._register_module(source, resolved, m.version)

    def _handle_alias(self, name: str, use: str, target: str) -> None:
        if use != "use":
            raise PlanSyntaxError("syntax error, missing use in @alias")
        self._plan.aliases[name] = target

    def _handle_for(self, name: str, use: str, modref: str, source: str) -> None:
        if use != "use":
            raise PlanSyntaxError("syntax error, missing use in @for")
        resolved = self._resolve_variables(modref)
        m = ModuleRef.parse(resolved)
        full_key = f"{name}={m.module}"
        self._plan.modules[full_key] = PlanEntry(
            module=full_key, ref_str=resolved, source=source
        )
        if full_key not in self._plan.load_order:
            self._plan.load_order.append(full_key)

    def _handle_ref(self, name: str, as_: str, other: str, source: str) -> None:
        if as_ != "as":
            raise PlanSyntaxError("syntax error, missing as in @ref")

        other_ref_str = self._plan.modules.get(other, PlanEntry(other, other)).ref_str
        # resolve other's ref to a plan entry
        other_ref = ModuleRef.parse(other_ref_str)
        variant = other_ref.variant
        kind = other_ref.kind
        version = other_ref.version

        m = ModuleRef.parse(name)
        module = m.module
        ref_str = module
        if variant != "default":
            ref_str += f"/{variant}"
        if version != "NONE":
            if kind == RefKind.VERSION:
                ref_str += f":#{version}"
            else:
                ref_str += f":{version}"

        self._register_module(source, ref_str, version)

    def _handle_set(self, var: str, eq: str, value: str) -> None:
        if var and eq == "=":
            self._variables[var] = value

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def _handle_group_open(
        self,
        modref: str,
        arg1: str,
        arg2: str,
        arg3: str,
        arg4: str,
        source: str,
    ) -> None:
        if modref == "[":
            if not arg1:
                self._group_state = "yes"
            elif arg1 == "=":
                self._group_state = self._evaluate_barrier_group(arg2, arg3, arg4)
            elif arg1 == "/=":
                self._group_state = self._evaluate_inverse_barrier_group(
                    arg2, arg3, arg4
                )
            else:
                raise PlanSyntaxError(
                    f"build plan unexpected {arg1} on group start"
                )
        else:
            c = stripped = modref
            c = c[1:].strip()
            if c.startswith("="):
                discs = c[1:].strip()
                self._group_state = self._evaluate_barrier_group(discs, "", "")
            elif c.startswith("/="):
                discs = c[2:].strip()
                self._group_state = self._evaluate_inverse_barrier_group(
                    discs, "", ""
                )
            else:
                self._group_state = "yes"

    def _evaluate_barrier_group(
        self, disc1: str, disc2: str, disc3: str
    ) -> str:
        for d in [disc1, disc2, disc3]:
            if d and self._check_barrier("", d):
                return "yes"
        return "closed"

    def _evaluate_inverse_barrier_group(
        self, disc1: str, disc2: str, disc3: str
    ) -> str:
        for d in [disc1, disc2, disc3]:
            if d and self._check_barrier("", d):
                return "closed"
        return "yes"

    def _handle_group_member(self, line: str, source: str) -> None:
        if self._group_state == "yes":
            self._group_modules.append((line, source))

    def _handle_group_close(self, modref: str, arg1: str, source: str) -> None:
        if self._group_state == "closed":
            self._group_state = "no"
            self._group_modules = []
            return

        if arg1:
            ref_str = self._resolve_variables(arg1)
        else:
            ref_str = self._resolve_variables(modref[1:])

        group_ref = ModuleRef.parse("name" + ref_str)
        rvariant = group_ref.variant
        rkind = group_ref.kind
        rversion = group_ref.version

        for member_line, mem_source in self._group_modules:
            member_line = self._resolve_variables(member_line)
            m = ModuleRef.parse(member_line)

            module = m.module
            variant = m.variant
            kind = m.kind
            version = m.version

            if version == "NONE" and variant == "default":
                existing = self._plan.modules.get(module)
                if existing is not None:
                    em = ModuleRef.parse(existing.ref_str)
                    module = em.module
                    variant = em.variant
                    kind = em.kind
                    version = em.version

            fref = ""

            if rvariant != "default":
                merged = self._merge_variant(variant, rvariant)
                fref += merged
            elif variant != "default":
                fref += f"/{variant}"

            if rversion != "NONE":
                if rkind == RefKind.VERSION:
                    fref += f":#{rversion}"
                else:
                    fref += f":{rversion}"
            elif version != "NONE":
                if kind == RefKind.VERSION:
                    fref += f":#{version}"
                else:
                    fref += f":{version}"

            final_ref = module + fref
            self._register_module(mem_source, final_ref, rversion)

        self._group_state = "no"
        self._group_modules = []

    # ------------------------------------------------------------------
    # Module registration
    # ------------------------------------------------------------------

    def _handle_module_ref(self, line: str, source: str) -> None:
        resolved = self._resolve_variables(line)
        m = ModuleRef.parse(resolved)
        self._register_module(source, resolved, m.version)

    def _register_module(self, source: str, ref_str: str, kind: str) -> None:
        m = ModuleRef.parse(ref_str)

        if kind == "skip" or m.version == "skip":
            self._plan.modules[m.module] = PlanEntry(
                module=m.module, ref_str=m.module, source=source, kind="skip"
            )
            return

        kind_str = ""
        if kind == "force":
            kind_str = "force"

        self._plan.modules[m.module] = PlanEntry(
            module=m.module, ref_str=ref_str, source=source, kind=kind_str
        )
        if m.module not in self._plan.load_order:
            self._plan.load_order.append(m.module)

    # ------------------------------------------------------------------
    # Variable resolution
    # ------------------------------------------------------------------

    _VAR_RE = re.compile(r"\$\{(\w+)\}|\$(\w+)")

    def _resolve_variables(self, s: str) -> str:
        def repl(m: re.Match) -> str:
            key = m.group(1) or m.group(2)
            return self._variables.get(key, m.group(0))

        return self._VAR_RE.sub(repl, s)

    # ------------------------------------------------------------------
    # Barrier / discriminant
    # ------------------------------------------------------------------

    def _check_barrier(self, variant: str, discs: str) -> bool:
        for d in discs.split(","):
            d = d.strip()
            if not d:
                continue
            if d in self.discriminants:
                continue
            if variant and d in variant.split("."):
                continue
            return False
        return True

    # ------------------------------------------------------------------
    # Variant merge
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_variant(cvariant: str, rvariant: str) -> str:
        rvariant = rvariant.replace("+", " +")
        rvariant = rvariant.replace("-", " -")
        rvariant = rvariant.replace(".", " .")

        ref = cvariant if cvariant != "default" else ""
        aref = ""
        dref: list[str] = []
        action: str | None = None

        for v in rvariant.split():
            if not v:
                continue
            if v.startswith("+"):
                action = "add"
                if aref:
                    aref += "."
                aref += v[1:]
            elif v.startswith("-"):
                action = "del"
                dref.append(v[1:])
            elif action == "add":
                if aref:
                    aref += "."
                aref += v
            elif action == "del":
                dref.append(v)
            else:
                ref = ""
                if aref:
                    aref += "."
                aref += v.replace(".", "")

        nref = aref

        for o in (ref.split(".") if ref else []):
            if o and o not in nref.split("."):
                if nref:
                    nref += "."
                nref += o

        for n in dref:
            if nref == n:
                nref = ""
            elif nref.startswith(n + "."):
                nref = nref[len(n) + 1:]
            elif nref.endswith("." + n):
                nref = nref[: -(len(n) + 1)]
            elif ("." + n + ".") in nref:
                nref = nref.replace("." + n + ".", ".")

        return f"/{nref}" if nref else ""
