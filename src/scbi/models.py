from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class RefKind(Enum):
    NONE = auto()
    DEV = auto()
    VERSION = auto()
    BRANCH = auto()

    def __str__(self) -> str:
        return self.name


@dataclass
class ModuleRef:
    module: str
    variant: str = "default"
    kind: RefKind = RefKind.NONE
    version: str = "NONE"

    def __str__(self) -> str:
        result = self.module
        if self.variant != "default":
            result += f"/{self.variant}"
        if self.kind == RefKind.VERSION:
            result += f":#{self.version}"
        elif self.kind == RefKind.BRANCH:
            result += f":{self.version}"
        elif self.kind == RefKind.DEV:
            result += ":dev"
        return result

    @staticmethod
    def parse(ref: str) -> ModuleRef:
        version_part = ""
        module_part = ref

        if ":" in ref:
            module_part, version_part = ref.rsplit(":", 1)

        if version_part:
            if version_part == "dev":
                kind = RefKind.DEV
                ver = "dev"
            elif version_part.startswith("#"):
                kind = RefKind.VERSION
                ver = version_part[1:]
            else:
                kind = RefKind.BRANCH
                ver = version_part
        else:
            kind = RefKind.NONE
            ver = "NONE"

        variant = "default"
        if "/" in module_part:
            idx = module_part.index("/")
            module = module_part[:idx]
            variant = module_part[idx + 1:]

            if variant == "":
                variant = "default"
        else:
            module = module_part

        return ModuleRef(
            module=module,
            variant=variant,
            kind=kind,
            version=ver,
        )


@dataclass
class PlanEntry:
    module: str
    ref_str: str
    source: str = ""
    kind: str = ""


@dataclass
class Plan:
    name: str
    modules: dict[str, PlanEntry] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    load_order: list[str] = field(default_factory=list)


@dataclass
class ParsedHookKey:
    variant: str = ""
    modifier: str = ""      # pre, post, or empty
    cross: bool = False
    base_hook: str = ""


@dataclass
class InheritMapping:
    no_variant: bool = False
    hooks: list[str] | None = None     # filter: only inherit these hooks
    name: str | None = None            # rename destination plugin


@dataclass
class Plugin:
    name: str
    hooks: dict[str, list[str] | dict] = field(default_factory=dict)
    variants: set[str] = field(default_factory=set)
    inherit: str | list[str] | None = None
    inherit_mappings: list[InheritMapping] | None = None
    modules: list[str] | None = None
    vcs: dict | None = None
    out_of_tree: bool | None = None
    prefix: str | None = None
    aliases: dict[str, str] = field(default_factory=dict)


class PlanError(Exception):
    pass


class PlanSyntaxError(PlanError):
    pass


class PlanNotFoundError(PlanError):
    pass


class PluginError(Exception):
    pass


class PluginNotFoundError(PluginError):
    pass


class PluginSyntaxError(PluginError):
    pass
