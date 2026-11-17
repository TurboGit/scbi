"""``--standalone``: port of ``create-standalone-package`` and
``copy-module-src-callback`` (scripts.d/5_tools).

The archive ``$SCBI_TMP/sa-<bdir>.tgz`` holds the driver (the Python
package in ``lib/`` and the ``bin/scbi`` wrapper), the runtime files, the
plan, the plug-in definitions (any format) and the sources
(VCS checkouts, archives, patches) of the modules and of their
dependencies, an environment file (``.scbi-env-std.yaml``) and a ``build``
script. The archive is built with this driver: the environment file is
the Python one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from scbi.bashcompat import words
from scbi.errors import Exit
from scbi.walker import Walker

#  bin/scbi of the archive: the embedded driver
WRAPPER = """#!/bin/bash
D=$(cd "$(dirname "$0")/.." && pwd)
SCBI_ARGV0="$0" PYTHONPATH=$D/lib${PYTHONPATH:+:$PYTHONPATH} exec python3 -m scbi "$@"
"""

ENV_FILE = '''#  Environment of the standalone package
vars:
  SCBI_ROOT: $PWD
  SCBI_BDIR: $SCBI_ROOT/builds
  SCBI_PREFIX: $SCBI_BDIR/install
  SCBI_ARCHIVES: $SCBI_BDIR/.archives
  SCBI_PATCH: $SCBI_BDIR/.patches
  SCBI_LOGS: $SCBI_BDIR/.logs
  SCBI_PLAN: '{plan}'
'''


def _cp(src: str, dst: str, preserve: bool = True) -> None:
    """``cp [-p] SRC DST`` (DST a directory or a file name)."""
    if os.path.isdir(dst):
        dst = os.path.join(dst, os.path.basename(src))
    (shutil.copy2 if preserve else shutil.copy)(src, dst)


class Standalone:
    def __init__(self, builder):
        self.b = builder
        self.d = builder.d

    def get(self, name: str) -> str:
        return self.d.get(name)

    def ilog(self, module: str, *msg: str) -> None:
        self.d.log.ilog(module, *msg)

    def elog(self, module: str, *msg: str) -> None:
        self.d.log.elog(module, *msg)

    def copy_patches(self, module: str, variant: str, kind: str, ref: str, modref: str, dest: Path) -> None:
        d = self.d
        Walker(self.b).load_module(modref)
        patches = d.runner().variant_values(
            module, variant, "patches", [self.get("PREFIX"), self.get("TARGET"), variant, kind, ref],
            d.plan, self.b.modules_list)
        for patch_file in words("\n".join(patches)):
            for path in (f"{self.get('SCBI_PATCH')}/{patch_file}",
                         f"{self.get('SCBI_PLUGINS')}/patches/{patch_file}"):
                if os.path.isfile(path):
                    _cp(path, str(dest / "builds" / ".patches"), preserve=False)
                    break
            else:
                self.elog(module, "patch", "filename", patch_file.rsplit("/", 1)[-1], "not found")

    def copy_module(self, argv: list[str], dest: Path) -> None:
        """``copy-module-src-callback``."""
        a = argv + [""] * 7
        formodule, modref, _level, _kind, is_ext = a[:5]
        module, variant, kind, ref = (self.d.plan.module_ref(modref, formodule) + [""] * 4)[:4]
        if is_ext == "true":
            with open(dest / "build-deps", "a") as f:
                f.write(f" {module}")
            return
        bdir = self.get("SCBI_BDIR")
        mdir = f"{bdir}/{module}"
        if not os.path.isdir(mdir):
            self.elog(module, "sources not found, cannot create archive")
            raise Exit(1)
        self.ilog("standalone", "-   " + module)
        #  two modules may share the same VCS or archive (the test of the
        #  Bash version looks in $DEST/.archives and $DEST/.vcs: never true)
        if os.path.islink(f"{mdir}/archive"):
            _cp(os.path.realpath(f"{mdir}/archive"), str(dest / "builds" / ".archives"))
        elif os.path.islink(f"{mdir}/vcs"):
            src = os.path.realpath(f"{mdir}/vcs")
            shutil.copytree(src, dest / "builds" / ".vcs" / os.path.basename(src), symlinks=True,
                            dirs_exist_ok=True)
        plugin = self.d.registry.plugin_file(module)
        if plugin is not None:
            _cp(str(plugin), str(dest / "scripts.d"))
            if self.get("DO_PATCH") == "yes":
                self.copy_patches(module, variant, kind, ref, modref, dest)

    def create(self, modules: list[str]) -> None:
        """``create-standalone-package``."""
        tmp = self.get("SCBI_TMP") or "/tmp"
        name = "sa-" + self.get("SCBI_BDIR").rsplit("/", 1)[-1]
        dest = Path(tmp, name)
        shutil.rmtree(dest, ignore_errors=True)
        self.ilog("standalone", "Create", "source", "archive", "in", str(dest))

        cwd = os.getcwd()
        try:
            #  a sub-shell in Bash: an exit stops the copy, not the archive
            dest.mkdir()
            os.chdir(dest)
            (dest / "build-deps").write_text("apt install")
            for sub in ("bin", "lib", "scripts.d", "builds/.vcs", "builds/.tar", "builds/.patches"):
                (dest / sub).mkdir(parents=True, exist_ok=True)
            import scbi

            shutil.copytree(Path(scbi.__file__).parent, dest / "lib" / "scbi",
                            ignore=shutil.ignore_patterns("__pycache__"))
            (dest / "bin" / "scbi").write_text(WRAPPER)
            os.chmod(dest / "bin" / "scbi", 0o755)
            plugins = Path(self.get("SCBI_PLUGINS"))
            for f in sorted(plugins.glob("[0-9]_*")):
                _cp(str(f), str(dest / "scripts.d"))
            plan = self.get("SCBI_PLAN")
            if plan:
                _cp(str(plugins / f".plan-{plan}"), str(dest / "scripts.d"))
            for module in words(" ".join(modules)):
                Walker(self.b).walk("for-all-modules-with-meta-ext",
                                    lambda argv: self.copy_module(argv, dest), module, str(dest),
                                    name="copy-module-src-callback")
            (dest / ".scbi-env-std.yaml").write_text(ENV_FILE.format(plan=plan.replace("'", "''")))
            mods = " ".join(words(" ".join(modules)))
            (dest / "build").write_text(
                "#!/bin/bash\n"
                "export PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -c1-3)\n"
                "export PATH=$PWD/bin:$PATH\n"
                f'SCBI_MODULES="{mods}"\n'
                '[[ -n $1 ]] && SCBI_MODULES="$*"\n'
                "./bin/scbi --env=std --deps $SCBI_MODULES\n")
            os.chmod(dest / "build", os.stat(dest / "build").st_mode | 0o100)
        except Exit:
            pass
        except OSError as e:
            self.elog("standalone", str(e))
        finally:
            os.chdir(cwd)

        subprocess.run(["tar", "cfz", f"{dest}.tgz", name], cwd=tmp, stderr=subprocess.DEVNULL)
        shutil.rmtree(dest, ignore_errors=True)
        self.ilog("standalone", "End", "create", "source", "archive")
