from __future__ import annotations

import os
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BuildEnv:
    module: str = ""
    variant: str = "default"
    version: str = "NONE"

    scbi_bdir: Path = field(default_factory=lambda: Path.cwd() / ".scbi-build")
    scbi_prefix: Path | None = None
    scbi_target: str = ""
    scbi_host: str = ""
    scbi_plugins: Path | None = None
    scbi_jobs: int = 0
    scbi_flat: bool = False
    scbi_enabled_features: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.scbi_host:
            self.scbi_host = platform.machine() + "-linux-gnu"
        if not self.scbi_target:
            self.scbi_target = self.scbi_host
        if self.scbi_jobs <= 0:
            self.scbi_jobs = os.cpu_count() or 1
        if self.scbi_prefix is None:
            self.scbi_prefix = self.scbi_bdir / "install"
        if self.scbi_plugins is None:
            self.scbi_plugins = Path.cwd() / "scripts.d"

    @property
    def tvdv(self) -> str:
        return f"{self.scbi_target}-{self.variant}"

    @property
    def module_root(self) -> Path:
        return self.scbi_bdir / self.module

    @property
    def tvdv_dir(self) -> Path:
        return self.module_root / self.tvdv

    @property
    def shared_src_dir(self) -> Path:
        return self.module_root / "src"

    @property
    def src_dir(self) -> Path:
        return self.tvdv_dir / "src"

    @property
    def build_dir(self) -> Path:
        return self.tvdv_dir / "build"

    @property
    def install_dir(self) -> Path:
        return self.tvdv_dir / "install"

    @property
    def logs_dir(self) -> Path:
        return self.tvdv_dir / "logs"

    def ensure_dirs(self) -> None:
        self.module_root.mkdir(parents=True, exist_ok=True)
        self.tvdv_dir.mkdir(parents=True, exist_ok=True)
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def is_cross(self) -> bool:
        return self.scbi_host != self.scbi_target

    def is_enabled(self, name: str) -> bool:
        key = name.replace("-", "_")
        val = self.scbi_enabled_features.get(key)
        if val is not None:
            return val == "true"
        return False

    def has_variant(self, variant_dot: str, target: str) -> bool:
        return target in variant_dot.split(".")

    def system_compiler(self) -> dict[str, str]:
        return {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "C_INCLUDE_PATH": "",
            "CPLUS_INCLUDE_PATH": "",
            "LIBRARY_PATH": "",
            "LD_LIBRARY_PATH": "",
            "ADA_PROJECT_PATH": "",
        }

    @staticmethod
    def get_version_number(value: str) -> str:
        normalized = value.replace("_", ".")
        m = re.match(
            r"[^0-9-]*(-?\d*(\.\d*)?(\.\d*)?).*", normalized
        )
        if m:
            num_str = m.group(1)
            letters = len(value) - len(num_str)
            if letters > 5 or num_str.endswith("."):
                return "0"
            return num_str if num_str else "0"
        return "0"

    def substitute(self, text: str) -> str:
        result = (
            text.replace("$PREFIX", str(self.scbi_prefix))
            .replace("$TARGET", self.scbi_target)
            .replace("$HOST", self.scbi_host)
            .replace("$VARIANT", self.variant)
            .replace("$VERSION", self.version)
            .replace("$JOBS", str(self.scbi_jobs))
            .replace("$SCBI_BDIR", str(self.scbi_bdir))
            .replace("$TVDIR", str(self.tvdv_dir))
        )
        result = re.sub(
            r'\$\{(\w+)\}|\$(\w+)',
            lambda m: os.environ.get(m.group(1) or m.group(2), m.group(0)),
            result,
        )
        return result
