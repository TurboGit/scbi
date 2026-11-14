"""scbi source-archive: create a source archive of modules from their VCS
(port of scbi-source-archive, on top of scbi.sources).

Quirks of the Bash tool kept: get-vcs is called with FORMODULE "ROOT",
the module log is named after the module reference given on the command
line, a native variant replaces the build plan by the module only, an
error for a module does not change the exit status.
"""

from __future__ import annotations

import glob as _glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

from scbi.bashcompat import words

USAGE = """
SCBI-SOURCE-ARCHIVE {version}

{argv0} source-archive [options] plug-in1 [plug-in2...]

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --plugins=<dir>    specify the plugins' directory
   -e | --env=<name>       environment file ~/.scbi-<name>
      | --plan=<name>      a build plan for modules
   -c | --clean-version    use only numbers/dots in version
      | --md5              create a md5 for the archive
      | --sha1             create a sha-1 for the archive
      | --sha256           create a sha-256 for the archive
   -l | --lower-case       for lower-case archive name"""

#  (pattern suffix, compressor or None, FILE: basename suffix removed)
FORMATS = [
    ("tgz", None), ("tar.gz", "gzip"), ("tar.bz2", "bzip2"), ("tar.zst", "zstd"),
    ("tar.xz", "xz"), ("tar", None), ("zip", None),
]


def out(text: str = "") -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def _basename(path: str, suffix: str = "") -> str:
    name = os.path.basename(path.rstrip("/")) if path.strip("/") else ("/" if path else "")
    if suffix and name.endswith(suffix) and name != suffix:
        name = name[: -len(suffix)]
    return name


def main(driver, args: list[str]) -> int:
    proc = subprocess.run(
        ["getopt", "-u", "-o", "cl", "-l", "clean-version,lower-case,sha1,sha256,md5",
         "--", *words(" ".join(args))],
        capture_output=True, text=True, env=driver.base_env())
    if proc.returncode != 0:
        sys.stdout.write(proc.stderr)
        print('try "scbi source-archive --help" for more information.')
        return 1
    clean, lower, sha = "no", "no", "no"
    for a in words(proc.stdout):
        if a in ("-c", "--clean-version"):
            clean = "yes"
        elif a in ("--md5", "--sha1", "--sha256"):
            sha = a[2:]
        elif a in ("-l", "--lower-case"):
            lower = "yes"

    modules = words(" ".join(driver.modules))
    if driver.get("DO_HELP") == "yes" or not modules:
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0

    from scbi.build import Builder

    builder = Builder(driver)
    for module in modules:
        handle_module(driver, builder, module, module, clean, lower, sha)
    return 0


def handle_module(driver, builder, modref: str, loop_module: str, clean: str, lower: str, sha: str) -> None:
    """``sar-handle-module MODREF`` (its sub-shell: plan, directory and
    variables restored after)."""
    workdir = tempfile.mkdtemp(dir="/dev/shm" if os.path.isdir("/dev/shm") else None)
    #  log=$WORKDIR/$module.log with $module the loop variable
    driver.set("log", f"{workdir}/{loop_module}.log", export=True)
    driver.set("SCBI_BDIR", workdir, export=True)
    cdir = os.getcwd()
    saved_modver = dict(driver.plan.modver)
    try:
        os.chdir(workdir)
        _handle(driver, builder, modref, cdir, clean, lower, sha)
    finally:
        os.chdir(cdir)
        driver.plan.modver.clear()
        driver.plan.modver.update(saved_modver)
        shutil.rmtree(workdir, ignore_errors=True)


def _handle(driver, builder, modref, cdir, clean, lower, sha) -> None:
    from scbi.sources.data import archive_data, vcs_data
    from scbi.sources.handle import Sources

    module, variant, kind, ref = (driver.plan.module_ref(modref, "@root") + [""] * 4)[:4]
    if ref == "NONE":
        ref = "master"
    if variant == "native":
        variant = "default"
        modref = f"{module}:{ref}"
        #  the reference is forced to get the vcs of the default variant
        driver.plan.modver.clear()
        driver.plan.modver[module] = modref

    os.makedirs(module, exist_ok=True)
    #  echo Create source archive for $module \[${variant//./ }\] \($ref\)
    out(" ".join(words(f"Create source archive for {module} [{variant.replace('.', ' ')}] ({ref})")))

    if driver.registry.plugin_file(module) is None:
        out(f"error: cannot find {module} plugin")
        return
    driver.registry.load_module(module)
    builder.load_module(module, variant)

    vcs, _ = vcs_data(builder, module, variant)
    name = vcs[3] if len(vcs) > 3 else ""
    if kind == "BRANCH" and not vcs:
        out(f"error: {module}-vcs function not defined, cannot get vcs")
        return

    src = Sources(builder, "ROOT", modref)
    if src.get_vcs() != 0:
        vdir = f"{workdir_of(driver)}/{module}/vcs"
        if not os.path.isdir(vdir):
            #  cd $SCBI_BDIR/$module/vcs fails, the commands run in $WORKDIR
            sys.stdout.flush()
            sys.stderr.write(f"scbi-source-archive: line 1: cd: {vdir}: No such file or directory\n")
            sys.stderr.flush()
        if name == "git":
            out("Possible tags found")
            #  git tag | grep $(echo $REF | sed "s/[A-Z]\|[a-z]//g")
            cwd = vdir if os.path.isdir(vdir) else None
            tags = subprocess.run(["git", "tag"], cwd=cwd, env=driver.base_env(), stdout=subprocess.PIPE).stdout
            subprocess.run(["grep", *re.sub("[A-Za-z]", "", ref).split()], input=tags, cwd=cwd,
                           env=driver.base_env())
        return

    mdir = f"{workdir_of(driver)}/{module}"
    os.chdir(mdir)

    if clean == "yes":
        #  echo $REF | sed "s/[A-Z]\|[a-z]//g;s/_/\./g"
        ref = " ".join(re.sub("[A-Za-z]", "", ref).replace("_", ".").split())
        ref = ref.split("-", 1)[0]

    tar, _ = archive_data(builder, module, variant, ref)
    url = vcs[4] if len(vcs) > 4 else ""
    rep = _basename(url)
    archive_name = rep
    if name == "git":
        rep = _basename(rep, ".git")
        archive_name = _basename(_basename(archive_name, ".git"), ".bundle")
    archive_name = f"{archive_name}-{ref}.tar.gz"
    if tar:
        archive_name = tar[5] if len(tar) > 5 else ""
    if lower == "yes":
        archive_name = archive_name.lower()

    out(" ".join(["  from ", *words(url)]))
    out(" ".join(["    to ", *words(archive_name)]))

    if os.path.islink("src"):
        subprocess.run(["mv", "src", rep])
    else:
        subprocess.run(["mv", "vcs", rep])

    _create(archive_name, rep, cdir)

    if sha != "no":
        tool = {"md5": "md5sum", "sha1": "sha1sum", "sha256": "sha256sum"}[sha]
        with open(os.path.join(cdir, f"{archive_name}.{sha}"), "w") as f:
            subprocess.run([tool, *words(archive_name)], cwd=cdir, stdout=f)


def workdir_of(driver) -> str:
    return driver.get("SCBI_BDIR")


def _create(archive_name: str, rep: str, cdir: str) -> None:
    tar = ["tar", "--exclude-vcs", "--dereference", "--create", "--file"]
    for suffix, compressor in FORMATS:
        if not archive_name.endswith(suffix):
            continue
        if suffix == "tgz":
            f = f"{cdir}/{_basename(archive_name)}"
            _rm(f, f"{f}.tgz")
            subprocess.run(["tar", "--exclude-vcs", "--gzip", "--dereference", "--create", "--file", f, rep])
        elif suffix == "tar":
            f = f"{cdir}/{_basename(archive_name)}"
            _rm(f)
            subprocess.run([*tar, f, rep])
        elif suffix == "zip":
            f = f"{cdir}/{archive_name}"
            _rm(f"{f}.zip")
            #  rm -fr $REP/.git* $REP/.hg $REP/.svn
            for p in [*_glob.glob(f"{_glob.escape(rep)}/.git*"), f"{rep}/.hg", f"{rep}/.svn"]:
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p, ignore_errors=True)
                elif os.path.lexists(p):
                    os.unlink(p)
            subprocess.run(["zip", "-qr", f, rep])
        else:
            ext = suffix.rsplit(".", 1)[1]
            f = f"{cdir}/{_basename(archive_name, '.' + ext)}"
            _rm(f, f"{f}.{ext}")
            subprocess.run([*tar, f, rep])
            subprocess.run([compressor, "-9", f])
        return
    out("error: unknown archive format")


def _rm(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass
