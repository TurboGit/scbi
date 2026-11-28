"""Generic module steps: port of scripts.d/7_modgen (module-setup,
module-patch, module-apply-patch, module-purge, module-purge-tvdir,
module-pre-install, module-install) and of the 5_tools helpers they use
(sync-dir, module-clean-install).

The driver runs ``module-<step> PREFIX FORMODULE MODULE VARIANT TARGET
OOT 2>&1 | tee [-a] $log`` in a sub-shell from ``$SCBI_BDIR/<module>``;
``Generic.step`` does the same: the messages and the output of the
commands go to the console and to the module log, the current directory
is restored afterwards.
"""

from __future__ import annotations

import dataclasses
import glob
import hashlib
import os
import shutil
import subprocess
import sys
import time

from scbi.bashcompat import read_lines_escaped, words
from scbi.sources import buildid

#  steps with a generic implementation
STEPS = ("setup", "pre-install", "install", "purge")



def later_targets(entries, i: int) -> list[str]:
    """The targets of the source-tree entries after the i-th one inside its
    target, relative to it: not copied by the i-th entry (filled by the
    later ones)."""
    to = entries[i].to
    out: list[str] = []
    for later in entries[i + 1:]:
        if to == "." and later.to != ".":
            out.append(later.to)
        elif later.to.startswith(f"{to}/"):
            out.append(later.to[len(to) + 1:])
    return out

class Tee:
    """``2>&1 | tee [-a] FILE``: text to the console and to FILE."""

    def __init__(self, path: str, append: bool):
        self.path = path
        #  tee opens (and truncates) the file before any output
        try:
            open(path, "a" if append else "w").close()
        except OSError as e:
            sys.stderr.write(f"tee: {path}: {e.strerror}\n")

    def write(self, text: str) -> int:
        sys.stdout.write(text)
        sys.stdout.flush()
        try:
            with open(self.path, "a") as f:
                f.write(text)
        except OSError:
            pass
        return len(text)

    def flush(self) -> None:
        pass


class Generic:
    """The generic steps of a module (``tvdir``: its target directory)."""

    def __init__(self, builder, formodule: str, module: str, variant: str, tvdir: str):
        self.b = builder
        self.d = builder.d
        self.formodule = formodule
        self.module = module
        self.variant = variant
        self.tvdir = tvdir
        self.out = sys.stdout

    # ------------------------------------------------------------ helpers

    def get(self, name: str) -> str:
        return self.d.get(name)

    def log(self):
        """The logger writing to the step output (``2>&1 | tee``)."""
        return dataclasses.replace(self.d.log, stdout=self.out, stderr=self.out)

    def ilog(self, *msg: str) -> None:
        self.log().ilog(self.module, *msg)

    def elog(self, *msg: str) -> None:
        self.log().elog(self.module, *msg)

    def say(self, text: str) -> None:
        self.out.write(text)
        self.out.flush()

    def cmd(self, argv: list[str], stdin=None, stdout=None) -> int:
        """Run a command, its output (both streams) to the step output
        (stdout=DEVNULL: only the errors)."""
        try:
            proc = subprocess.run(argv, stdin=stdin, stdout=subprocess.PIPE if stdout is None else stdout,
                                  stderr=subprocess.STDOUT if stdout is None else subprocess.PIPE)
        except FileNotFoundError:
            self.say(f"{argv[0]}: command not found\n")
            return 127
        data = (proc.stdout if stdout is None else proc.stderr) or b""
        if data:
            self.say(data.decode(errors="replace"))
        return proc.returncode

    def cp(self, src: str, dst: str) -> bool:
        """``cp SRC DST``."""
        if not os.path.exists(src):
            self.say(f"cp: cannot stat '{src}': No such file or directory\n")
            return False
        try:
            shutil.copyfile(src, os.path.join(dst, os.path.basename(src)) if os.path.isdir(dst) else dst)
        except OSError as e:
            self.say(f"cp: cannot create regular file '{dst}': {e.strerror}\n")
            return False
        return True

    def ln(self, target: str, link: str) -> None:
        """``ln -s TARGET LINK``."""
        try:
            os.symlink(target, link)
        except OSError as e:
            self.say(f"ln: failed to create symbolic link '{link}': {e.strerror}\n")

    def realpath_relative(self, path: str, base: str) -> str | None:
        """``realpath --relative-to=BASE PATH`` (all components but the
        last must exist)."""
        for p in (path, base):
            parent = os.path.dirname(os.path.normpath(p)) or "."
            if not os.path.isdir(parent):
                self.say(f"realpath: {p}: No such file or directory\n")
                return None
        return os.path.relpath(os.path.realpath(path), os.path.realpath(base))

    def sync_dir(self, src: str, dst: str, *opts: str) -> int:
        """``sync-dir FROM TO [OPTS]``: rsync with hard links to FROM."""
        relto = self.realpath_relative(src, dst)
        if relto is None:
            relto = ""
        return self.cmd(["rsync", "-a", "--exclude=.git", "--exclude=.gitignore", "--exclude=.svn",
                         f"--link-dest={relto}", *words(" ".join(opts)), src, dst])

    def cached(self) -> bool:
        return self.b.fn_exists(f"{self.module}-cached")

    # -------------------------------------------------------------- steps

    def apply_patch(self, patch_file: str) -> int:
        """``module-apply-patch MODULE PATCH``."""
        if not patch_file:
            return 0
        name = patch_file.rsplit("/", 1)[-1]
        for path in (f"{self.get('SCBI_PATCH')}/{patch_file}", f"{self.get('SCBI_PLUGINS')}/patches/{patch_file}"):
            if os.path.isfile(path):
                break
        else:
            self.elog("patch", name, "not found")
            return 1
        self.ilog("apply", "patch", path.rsplit("/", 1)[-1])
        if shutil.which("patch") is None:
            self.say("Required tools patch missing, please install\n")
            raise SystemExit(1)
        with open(path, "rb") as f:
            res = self.cmd(["patch", "-p1"], stdin=f, stdout=subprocess.DEVNULL)
        if res != 0:
            self.elog("patch", name, "does not apply")
        return res

    def patch(self, prefix: str, target: str, modref: str) -> int:
        """``module-patch PREFIX TARGET MODREF``."""
        info = (self.d.plan.module_ref(modref) + ["", "", "", ""])[:4]
        module, variant, kind, ref = info
        patches = self.d.runner().variant_values(module, variant, "patches",
                                                 [prefix, target, variant, kind, ref],
                                                 self.d.plan, self.b.modules_list)
        res = 0
        for p in words("\n".join(patches).rstrip("\n")):
            if self.apply_patch(p) != 0:
                res = 1
        return res

    # ---------------------------------------------------------- source-tree

    def source_tree(self, prefix: str, target: str):
        """The entries of the source-tree hook of the module (guards and
        values evaluated), None without the hook."""
        from scbi.hooks.evaluate import eval_source_tree, set_plugin_vars
        from scbi.plugin.model import Values
        from scbi.plugin.resolve import get_hook

        runner = self.d.runner()
        fct = get_hook(self.d.registry, self.module, self.variant, "source-tree", runner.cross)
        body = self.d.registry.functions.get(fct) if fct else None
        if not isinstance(body, Values):
            return None
        ctx = runner.context(self.module, self.variant, "source-tree", [prefix, target, self.variant],
                             self.d.plan, self.b.modules_list)
        set_plugin_vars(ctx, self.d.registry.plugin_variables(self.module))
        return eval_source_tree(body, ctx)

    def dependency_names(self, prefix: str, target: str) -> set[str]:
        """The modules of the depends and build-depends hooks of the module
        (for its variant and the target), without variant nor version."""
        import re

        runner = self.d.runner()
        names: set[str] = set()
        for hook in ("depends", "build-depends"):
            values = runner.variant_values(self.module, self.variant, hook, [prefix, target, self.variant],
                                           self.d.plan, self.b.modules_list)
            for w in words("\n".join(values)):
                if not w.startswith("os@-"):
                    names.add(re.split(r"[/:]", w.split("=", 1)[-1], maxsplit=1)[0])
        return names

    def assemble(self, entries, root: str, prefix: str, target: str) -> tuple[int, str]:
        """The source tree ``root`` made of the entries, in order: each one
        mirrors its sources into its target (rsync --delete: the files
        removed upstream are removed, the unchanged ones keep their time),
        without its excludes, the VCS directories and the targets of the
        later entries inside it (filled by them). Returns the status and
        the directory of the module's own sources ("" if none)."""
        deps = self.dependency_names(prefix, target)
        for e in entries:
            if e.from_ and e.from_ != self.module and e.from_ not in deps:
                self.elog("source-tree:", e.from_, "is not a dependency (depends, build-depends)")
                return 1, ""
        own = ""
        for i, e in enumerate(entries):
            mine = not e.from_ or e.from_ == self.module
            if mine:
                src = "src"
            else:
                src = self.b.modules_dir.get(f"{e.from_}@src", "")
            if not src or not os.path.isdir(src):
                self.elog("source-tree:", "no", "sources", "for", e.from_ or self.module)
                return 1, ""
            dst = root if e.to == "." else f"{root}/{e.to}"
            excludes = list(e.exclude) + later_targets(entries, i)
            os.makedirs(dst, exist_ok=True)
            opts = ["--delete", "--exclude=.hg", "--exclude=CVS"] + [f"--exclude=/{x}" for x in excludes]
            if self.sync_dir(f"{src}/.", f"{dst}/", *opts) != 0:
                return 1, ""
            if mine:
                own = dst
        return 0, own

    def setup(self, prefix: str, target: str, oot: str) -> int:
        """``module-setup`` (run from $SCBI_BDIR/<module>)."""
        cached = self.cached()
        lnk = self.get("SCBI_LNK")
        tvdir = self.realpath_relative(self.tvdir, ".") or ""
        res = 0
        hassrc = True
        entries = self.source_tree(prefix, target)
        if entries is not None:
            #  the source tree made of the sources of several modules
            if not cached:
                res, own = self.assemble(entries, f"{tvdir}/src", prefix, target)
                if res != 0:
                    return res
                if os.path.isfile(f"source-id-{self.variant}"):
                    self.cp(f"source-id-{self.variant}", f"{tvdir}/source-id")
                if self.get("DO_PATCH") == "yes":
                    cwd = os.getcwd()
                    #  the patches of the module: in its own sources
                    os.chdir(own or f"{tvdir}/src")
                    try:
                        res = self.patch(prefix, target, self.module)
                    finally:
                        os.chdir(cwd)
        elif os.path.exists(f"src{lnk}") or os.path.isdir("src"):
            #  the sources of the module (several modules: source-tree)
            srcdir = f"{tvdir}/src"
            if not cached:
                if self.sync_dir("src/.", f"{srcdir}/", "--delete") == 0:
                    self.cp(f"source-id-{self.variant}", f"{tvdir}/source-id")
                if self.get("DO_PATCH") == "yes":
                    cwd = os.getcwd()
                    #  pushd $SRCDIR &> /dev/null: stays here on failure
                    if os.path.isdir(srcdir):
                        os.chdir(srcdir)
                    try:
                        res = self.patch(prefix, target, self.module)
                    finally:
                        os.chdir(cwd)
        else:
            hassrc = False

        _rm_rf("build")
        self.ln(tvdir, "build")
        if cached:
            return 0
        if oot == "true":
            if "mingw64" in self.get("SCBI_HOST"):
                if os.path.isdir(f"{tvdir}/build"):
                    _rm_rf(f"{tvdir}/build")
            elif os.path.islink(f"{tvdir}/build"):
                os.unlink(f"{tvdir}/build")
            try:
                os.makedirs(f"{tvdir}/build", exist_ok=True)
            except OSError as e:
                self.say(f"mkdir: cannot create directory '{tvdir}/build': {e.strerror}\n")
        else:
            _rm_rf(f"{tvdir}/build")
            if hassrc:
                self.ln("src", f"{tvdir}/build")
        return res

    def purge_tvdir(self, tvdir: str) -> None:
        """``module-purge-tvdir TVDIR`` (the manifest is kept)."""
        for f in ("build-id", "source-id", "build-deps", "binary-key", "binary-key.json"):
            _rm_f(f"{tvdir}/{f}")
        for f in ("build", "install", "src"):
            _rm_rf(f"{tvdir}/{f}")

    def purge(self, prefix: str) -> int:
        """``module-purge PREFIX ...`` (PREFIX: $SCBI_BDIR/<module>)."""
        tvdir = self.tvdir
        if os.path.isdir(tvdir):
            self.purge_tvdir(tvdir)
            _rm_rf(f"{prefix}/build-id-{self.variant}")
            _rm_rf(f"{prefix}/build-deps-{self.variant}")
            _rm_f(f"{prefix}/build")
        return 0

    def install_dir(self, mprefix: str, target: str) -> str:
        """The final installation directory (prefix hook or SCBI_PREFIX)."""
        runner = self.d.runner()
        for fct, args in ((f"{self.module}-{self.variant}-prefix", [mprefix, target]),
                          (f"{self.module}-prefix", [mprefix, target, self.variant])):
            if self.b.fn_exists(fct) and self.get("SCBI_DEFAULT_PREFIX") == "yes":
                lines = runner.call_value(fct, self.module, self.variant, args, self.d.plan, self.b.modules_list)
                return "\n".join(lines).rstrip("\n")
        return self.get("SCBI_PREFIX")

    def clean_install(self, mprefix: str, target: str) -> int:
        """``module-clean-install``: removes the files of the manifest from
        the final installation directory (never fails)."""
        idir = self.install_dir(mprefix, target)
        if idir == "NONE":
            return 0
        sudo = [] if os.access(idir, os.W_OK) else ["sudo"]
        manifest = f"{mprefix}/../manifest"
        if not os.path.isfile(manifest):
            return 0
        with open(manifest, errors="surrogateescape") as f:
            files = read_lines_escaped(f.read())
        dirs = set()
        for file in files:
            path = f"{idir}/{file}"
            if sudo:
                self.cmd([*sudo, "rm", "-f", path])
            else:
                try:
                    if os.path.lexists(path) and not os.path.isdir(path):
                        os.unlink(path)
                except OSError as e:
                    self.say(f"rm: cannot remove '{path}': {e.strerror}\n")
            dirs.add(file.rsplit("/", 1)[0] if "/" in file else file)
        for dname in sorted(dirs):
            subprocess.run(["rmdir", "--ignore-fail-on-non-empty", "--parents", f"{idir}/{dname}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #  "cd $MPREFIX && rm -fr ." in Bash: rm refuses to remove "."
        if (mprefix.rsplit("/", 1)[-1] == "install"
                and os.path.basename(os.path.dirname(mprefix)) == self.get("module")):
            self.say("rm: refusing to remove '.' or '..' directory: skipping '.'\n")
        return 0

    def pre_install(self, mprefix: str, target: str) -> int:
        """``module-pre-install``: the previous installation is removed."""
        return self.clean_install(mprefix, target)

    def install(self, prefix: str, target: str) -> int:
        """``module-install`` (run from $SCBI_BDIR/<module>)."""
        variant = self.variant
        if not os.path.isfile(f"build-id-{variant}"):
            if os.path.isdir("src"):
                vid = _md5(self._cat_src())
                bid = buildid.build_id(self.b, prefix, target, self.formodule, self.module, vid)
            else:
                bid = _md5((time.strftime("%c") + "").encode())
            with open(f"build-id-{variant}", "w") as f:
                #  get-build-id prints no newline, md5sum | cut does
                f.write(bid if os.path.isdir("src") else bid + "\n")
        if os.path.isdir("build/install"):
            #  find . -type f > ../manifest (in build/install)
            with open("build/manifest", "w") as f:
                f.write("".join(p + "\n" for p in _find_files("build/install", ".")))
        if self.get("DO_BUILD") != "no":
            tvdir = self.tvdir
            self.cp(f"build-id-{variant}", f"{tvdir}/build-id")
            self.cp(f"source-id-{variant}", f"{tvdir}/source-id")
            if os.path.isfile(f"build-deps-{variant}"):
                self.cp(f"build-deps-{variant}", f"{tvdir}/build-deps")
        return 0

    def _cat_src(self) -> bytes:
        """``cat src/*``: the content of the files, an error message for
        the directories."""
        data = b""
        entries = sorted(glob.glob("src/*"))
        if not entries:
            self.say("cat: 'src/*': No such file or directory\n")
        for e in entries:
            if os.path.isdir(e):
                self.say(f"cat: {e}: Is a directory\n")
                continue
            try:
                with open(e, "rb") as f:
                    data += f.read()
            except OSError as err:
                self.say(f"cat: {e}: {err.strerror}\n")
        return data

    # ------------------------------------------------------------ driver

    def step(self, step: str, log: str | None, append: bool = True) -> int:
        """``cd $SCBI_BDIR/<module>; module-<step> ... 2>&1 | tee [-a] $log``
        in a sub-shell: the status of module-<step> (no log: output to the
        console only, for module-purge)."""
        prefix = f"{self.tvdir}/install"
        target = self.get("SCBI_TARGET")
        oot = self.get("SCBI_ISOOT")
        self.out = Tee(log, append) if log else sys.stdout
        cwd = os.getcwd()
        try:
            os.chdir(f"{self.get('SCBI_BDIR')}/{self.module}")
            if step == "setup":
                return self.setup(prefix, target, oot)
            if step == "pre-install":
                return self.pre_install(prefix, target)
            if step == "install":
                return self.install(prefix, target)
            if step == "purge":
                return self.purge(f"{self.get('SCBI_BDIR')}/{self.module}")
            raise ValueError(step)
        except SystemExit as e:
            #  exit in the sub-shell
            return int(e.code or 0)
        finally:
            os.chdir(cwd)
            self.out = sys.stdout


def _find_files(root: str, rel: str) -> list[str]:
    """``find REL -type f`` from ROOT: regular files (not symbolic links)
    in directory order, depth first."""
    out = []
    try:
        entries = list(os.scandir(os.path.join(root, rel)))
    except OSError:
        return out
    for e in entries:
        path = f"{rel}/{e.name}"
        if e.is_file(follow_symlinks=False):
            out.append(path)
        elif e.is_dir(follow_symlinks=False):
            out += _find_files(root, path)
    return out


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _rm_f(path: str) -> None:
    if os.path.lexists(path) and not os.path.isdir(path) or os.path.islink(path):
        os.unlink(path)


def _rm_rf(path: str) -> None:
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
