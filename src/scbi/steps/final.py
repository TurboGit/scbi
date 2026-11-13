"""The final step of a module with a Python environment file:
``module_final_step(ctx)`` (scbi.envpy) is called after each module, as
the Bash ``module-final-step PREFIX TARGET VARIANT MODULE DEPENDS_KIND
IS_META IS_AGGREGATED IS_UP_TO_DATE``.
"""

from __future__ import annotations

from dataclasses import dataclass

from scbi.bashenv import quote


@dataclass
class FinalStep:
    """What ``module_final_step(ctx)`` receives.

    Attributes: ``prefix`` (installation directory of the module),
    ``target``, ``variant``, ``module``, ``formodule`` (the module it is
    built for, ``@root`` at the top), ``modref``, ``depends_kind``,
    ``is_meta``, ``is_aggregated`` and ``is_up_to_date`` (the strings the
    Bash function receives: "yes"/"no", the aggregation mode...).
    """

    builder: object
    prefix: str
    target: str
    variant: str
    module: str
    formodule: str
    modref: str
    depends_kind: str
    is_meta: str
    is_aggregated: str
    is_up_to_date: str

    def get(self, name: str, default: str = "") -> str:
        """A driver variable (SCBI_BDIR, SCBI_IS_WINDOWS...)."""
        return self.builder.get(name) or default

    def is_enabled(self, feature: str) -> bool:
        """``is-enabled FEATURE`` for the module."""
        from scbi.hooks import builtins

        return builtins.is_enabled(self.builder.ctx(self.module, self.variant), feature)[0]

    def module_ref(self, modref: str, formodule: str = "@root") -> tuple[str, str, str, str]:
        """``get-module-ref``: (module, variant, kind, ref) of ``modref``
        in the plan (as seen from ``formodule``)."""
        info = (self.builder.d.plan.module_ref(modref, formodule or "@root") + [""] * 4)[:4]
        return info[0], info[1], info[2], info[3]

    def module_name(self, modref: str) -> str:
        """``get-module-name``: module[/variant][:ref] in the plan."""
        return self.builder.module_name(modref, self.formodule)

    def target_dir(self, module: str, variant: str, sub: str = "") -> str:
        """``get-target-dir``: the build directory of a module/variant."""
        return self.builder.target_dir(module, variant, sub)

    def ilog(self, *msg: str) -> None:
        """A message in the console and the module report."""
        self.builder.ilog(self.module, *msg)

    def env_actions(self, hook: str = "env", modref: str | None = None) -> list[tuple[str, str, str]]:
        """The environment actions (ACTION, VAR, VALUE) of the ``hook``
        hooks (env, build-env...) of ``modref`` (default: the module),
        aggregated modules of a meta-module included, in order, as
        ``plugin-call-env-hooks FORMODULE MODREF HOOK`` makes them. The SET
        actions are applied while the hooks run (a following hook sees the
        value), the others are only returned."""
        b = self.builder
        modref = modref or self.modref
        #  the module's environment hooks run with a recording define-var
        #  (Bash until the environment walker is ported)
        #  a SET is applied (as export) so that the following hooks see it
        code = ("function define-var() { printf '%s\\0%s\\0%s\\0' \"$1\" \"$2\" \"$3\" >&3\n"
                "  [[ $1 == SET || $1 == S ]] && export \"$2=$3\"; true; }\n"
                f"plugin-call-env-hooks {quote(self.formodule)} {quote(modref)} {quote(hook)} 3>&1 >/dev/null 2>&1")
        data = b.capture_raw(self.module, self.variant, code)
        items = data.split("\0")
        return [tuple(items[i:i + 3]) for i in range(0, len(items) - 2, 3)]
