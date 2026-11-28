"""The sources of a module (port of handle-sources, and of get-vcs,
get-branch, vcs-build-id and get-vcs-ref of scripts.d/4_scm).

Dispatch only: the VCS and archive work is done by the implementations
selected through scbi.sources.vcs.registry and scbi.sources.archive.

Run in $SCBI_BDIR/<module>; returns the exit status (``exit 1`` in Bash
ends the module). DO_UPDATE set here is a driver variable seen by the
following steps, as in Bash.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import time

from scbi.bashcompat import read_lines_escaped, words
from scbi.sources import buildid
from scbi.sources.archive.fetch import check_tool, get_archive, verify_sha256
from scbi.sources.data import archive_data, archive_exists, display_ref, user_co_dir, vcs_data
from scbi.sources.run import Run, command_env
from scbi.sources.vcs import registry

def read_content(path: str) -> str:
    """``read-content VAR FILE``: first line (``read`` without -r)."""
    try:
        with open(path, errors="surrogateescape") as f:
            text = f.read()
    except OSError:
        return ""
    if not text.endswith("\n"):
        text += "\n"
    lines = read_lines_escaped(text)
    return lines[0] if lines else ""


def _write(path: str, text: str, mode: str = "w") -> None:
    with open(path, mode) as f:
        f.write(text)


def _basename(path: str, suffix: str = "") -> str:
    name = os.path.basename(path.rstrip("/")) if path.strip("/") else ("/" if path else "")
    if suffix and name.endswith(suffix) and name != suffix:
        name = name[: -len(suffix)]
    return name


class Sources:
    def __init__(self, builder, formodule: str, modref: str):
        self.b = builder
        self.d = builder.d
        self.formodule = formodule
        self.modref = modref
        info = (self.d.plan.module_ref(modref, formodule) + [""] * 4)[:4]
        self.module, self.variant, self.kind, self.ref = info

    # ------------------------------------------------------------ helpers

    def get(self, name: str) -> str:
        return self.d.get(name)

    def out(self, line: str) -> None:
        self.b.out(line)

    def ilog(self, module: str, *msg: str) -> None:
        self.d.log.ilog(module, *msg)

    def run(self, log, proxy: str, logger=None) -> Run:
        """The context of VCS commands, output appended to the log."""
        env = command_env(self.b, self.module, self.variant, proxy)
        return Run.to_log(env, self.get("SCBI_BDIR"), log, logger or self.d.log, self._mail)

    def _mail(self, msg: str) -> None:
        """``send-mail MSG``."""
        if self.get("SCBI_EMAIL_NOTIFICATION") == "yes":
            import subprocess

            subprocess.run(["mail", "-s", msg, *words(self.get("SCBI_EMAIL"))],
                           input=time.strftime("%c") + "\n", text=True, env=self.d.base_env())

    def build_id(self, vid: str) -> str:
        return buildid.build_id(self.b, self.get("SCBI_PREFIX"), self.get("SCBI_TARGET"),
                                self.formodule, self.modref, vid)

    def epoch(self) -> str:
        return str(int(time.time()))

    # ------------------------------------------------------------ vcs

    def internal_get_branch(self, name: str, proxy: str, options: str, kind: str, ref: str,
                            dir: str, quiet: bool = False, fetch: bool = True) -> int:
        """``_internal_get-branch`` (``quiet``: its output to /dev/null,
        the branch commands still write to the log; ``fetch``: get the new
        tags from the remote first)."""
        impl = registry.get(name)
        #  quiet: the console output goes to /dev/null, the report log is
        #  still written
        logger = dataclasses.replace(self.d.log, stdout=_NULL) if quiet else self.d.log

        def ilog(*m: str) -> None:
            logger.ilog("build", *m)
        if impl is None:
            ilog(f"error: unknown vcs {name}")
            return 1
        if kind == "DEV":
            return 0
        with open(self.get("log"), "a") as log:
            if impl.branch(self.run(log, proxy), options, self.module, ref, dir, fetch=fetch) != 0:
                ilog(f"error: cannot switch to branch {ref}")
                return 1
        return 0

    def get_vcs(self) -> int:
        """``get-vcs``: checkout/update and switch to the reference; an
        error ends the module (returns 1)."""
        vcs, _ = vcs_data(self.b, self.module, self.variant)
        proxy, options, name, url, dir = (vcs[1:6] + [""] * 5)[:5]
        impl = registry.get(name)
        log_path = self.get("log")
        if impl is None:
            self.ilog("build", f"error: unknown vcs {name}")
            return 1
        #  an existing clone is updated from its remote by checkout (git fetch
        #  --tags); a new clone may lack the tags not on a branch: fetched by
        #  branch
        #  already fetched by the prefetch (--update:prefetch, waiting for its
        #  job first): no fetch at all
        prefetcher = getattr(self.b, "prefetcher", None)
        prefetched = prefetcher is not None and impl.names[0] == "git" \
            and prefetcher.vcs_result(dir, url, log_path) is not None
        repo = dir or _basename(url, ".git")
        fetch = not prefetched and not os.path.isdir(f"{self.get('SCBI_BDIR')}/.vcs/{repo}")
        with open(log_path, "a") as log:
            rc = impl.checkout(self.run(log, proxy), url, options, self.module, dir, fetch=not prefetched)
        if rc != 0:
            if check_tool(impl.tool, self.d.base_env()):
                self.ilog("build", f"error: cannot get sources from {url}")
            else:
                self.ilog("build", f"error: tool {impl.tool} not installed")
            self.ilog("build", f"error: see {log_path}")
            return 1
        return self.internal_get_branch(name, proxy, options, self.kind, self.ref, dir, fetch=fetch)

    def get_branch(self) -> int:
        """``get-branch ... &> /dev/null``: without --update, no access to
        the remote (a new reference sets --update for the module: handle)."""
        vcs, _ = vcs_data(self.b, self.module, self.variant)
        proxy, options, name, _url, dir = (vcs[1:6] + [""] * 5)[:5]
        return self.internal_get_branch(name, proxy, options, self.kind, self.ref, dir, quiet=True,
                                        fetch=False)

    def vcs_build_id(self, vcsdir: str) -> str:
        """``vcs-build-id PREFIX TARGET FORMODULE MODREF DIR``."""
        if not os.path.isdir(vcsdir):
            return buildid.string_md5(self.modref)
        vid = ""
        if self.get("DO_UPDATE") == "no":
            if self.get_branch() == 1:
                vid = buildid.string_md5(self.epoch())
        impl = registry.detect(vcsdir)
        if impl is not None:
            with open(os.devnull, "w") as null:
                r = Run.to_log(command_env(self.b, self.module, self.variant, ""), self.get("SCBI_BDIR"),
                               null, self.d.log)
                r.cwd = os.path.abspath(vcsdir)
                vid += impl.source_id(r)
        else:
            vid = "0"
        return self.build_id(vid)

    def vcs_ref(self, name: str, ref: str, dir: str) -> str:
        """``get-vcs-ref NAME REF DIR``."""
        impl = registry.get(name)
        text = f"{impl.label} {display_ref(name, ref)} {impl.id_kind} " if impl else ""
        if not os.path.isdir(dir):
            return text + "\n"
        if impl is None:
            return text
        cid = impl.commit_id(False, dir, self.d.base_env())
        return text + (cid + "\n" if cid else "")

    # ------------------------------------------------------------ main

    def handle(self) -> int:
        module, variant, kind, ref = self.module, self.variant, self.kind, self.ref
        lnk = self.get("SCBI_LNK")

        if variant == "native":
            _write(f"source-id-{variant}", f"native-{ref}")
            _write("source-ref", f"{module} none native revision {ref}\n")
            return 0

        _rm_f("source-ref")

        if kind == "BRANCH" and self.get("ARCHIVE_CACHE") == "yes":
            if archive_exists(self.b, module, variant, ref):
                kind = "VERSION"

        hassrc = "yes"

        if kind == "VERSION":
            tar, _ = archive_data(self.b, module, variant, ref)
            nv = len(tar)
            if nv == 0:
                self.out(f"error: {module}-archive function not defined, cannot get archive")
                return 1
            if nv not in (6, 7):
                v = "" if tar[0] == "default" else f"{tar[0]}-"
                self.out(f"error: {module}-{v}archive function returned {nv - 1} values, 5 or 6 expected")
                return 1
            tarsrc = tar[5]
            if tarsrc.upper() == "NONE":
                hassrc = "no"
            if os.path.isdir("archive-src"):
                abn = os.path.basename(os.path.realpath("archive"))
                if tarsrc != abn:
                    for p in (f"archive-sha1{lnk}", f"archive{lnk}", "archive-src"):
                        _rm_rf(p)
            if os.path.isfile(f"source-id-{variant}"):
                siv = read_content(f"source-id-{variant}")
                if siv != f"archive-{ref}" or hassrc == "no":
                    _rm_rf("archive-src")
            if hassrc == "yes":
                if (self.get("DO_UPDATE") == "yes" or not os.path.isdir("archive-src")
                        or not os.path.exists(f"archive{lnk}")):
                    v = tar[0][len("default"):] if tar[0].startswith("default") else tar[0]
                    self.ilog(module, "get", "sources", "from", "archive", *([f"[{v}]"] if v else []))
                    log = self.get("log")

                    def tee(line: str) -> None:
                        #  the messages of get-archive (ilog): already in the
                        #  report log, to the console only
                        self.out(line)

                    if get_archive(self.b, module, variant, ref, log, tee) != 0:
                        #  grep FAILED $log
                        try:
                            with open(log, errors="replace") as f:
                                for line in f:
                                    if "FAILED" in line:
                                        self.out(line.rstrip("\n"))
                        except OSError:
                            pass
                        self.ilog(module, "cannot", "get/find/extract", "archive", "sources")
                        return 1
                else:
                    #  extracted before: checked again when the SHA-256 of
                    #  the plug-in or the archive changed
                    def elog(*msg: str) -> None:
                        self.d.log.elog(module, *msg)

                    proto, url = (tar + [""] * 5)[3:5]
                    if not verify_sha256(self.b, module, variant, ref, self.get("SCBI_ARCHIVES"), tarsrc,
                                         os.getcwd(), elog,
                                         downloadable=proto.upper() != "NONE" and url.upper() != "NONE"):
                        self.ilog(module, "cannot", "get/find/extract", "archive", "sources")
                        return 1
                _write(f"source-id-{variant}", f"archive-{ref}")
                shutil.copyfile(f"source-id-{variant}", "source-id")
                archive_sha1 = "NONE"
                if os.path.exists(f"archive-sha1{lnk}"):
                    archive_sha1 = read_content("archive-sha1").split(" ", 1)[0]
                _write("source-ref", f"{module} archive {ref} sha-1 {archive_sha1.split(' ', 1)[0]}\n")
                _write(f"build-id-{variant}", self.build_id(f"archive-{ref}{archive_sha1}"))
                self._ln("archive-src", "src")
        else:
            vcs, _ = vcs_data(self.b, module, variant)
            nv = len(vcs)
            if nv not in (0, 5, 6):
                v = "" if vcs[0] == "default" else f"{vcs[0]}-"
                self.out(f"error: {module}-{v}vcs function returned {nv - 1} values, 4 or 5 expected")
                return 1
            name = vcs[3] if nv > 3 else ""
            url = vcs[4] if nv > 4 else ""
            if nv > 0 and name.upper() != "NONE":
                repo = _basename(url, ".git")
                if kind == "DEV":
                    user_repo = user_co_dir(self.b, name)
                    if user_repo == "NONE":
                        self.d.log.elog(*words(f"{self.get('MODULE')} unsupported VCS {name}"))
                        return 1
                    if os.path.isdir(f"{user_repo}/{repo}"):
                        self._ln(f"{user_repo}/{repo}", "vcs")
                        rdev = ""
                        if ref == "dev":
                            impl = registry.get(name)
                            cid = impl.commit_id(True, "vcs", self.d.base_env()) if impl else ""
                            rdev = f"-{cid}"
                        _write(f"source-id-{variant}", f"{ref}{rdev}")
                        shutil.copyfile(f"source-id-{variant}", "source-id")
                        _write(f"build-id-{variant}", self.vcs_build_id("vcs"))
                    else:
                        self.ilog(module, "cannot", "find", "local", "dev", "repository:")
                        self.ilog(module, *words(f"{user_repo}/{repo}"))
                        return 1
                else:
                    if self.get("DO_TEST") != "yes-only":
                        if os.path.isfile("source-id"):
                            if read_content("source-id") != f"vcs-{ref}":
                                self.d.set("DO_UPDATE", "yes")
                        else:
                            self.d.set("DO_UPDATE", "yes")
                    if self.get("DO_UPDATE") == "yes" or not os.path.isdir(f"../.vcs/{repo}"):
                        v = vcs[0][len("default"):] if vcs[0].startswith("default") else vcs[0]
                        self.ilog(module, "get", "sources", "from", *words(name), *([f"[{v}]"] if v else []))
                        if self.get_vcs() != 0:
                            return 1
                    else:
                        self._ln(f"../.vcs/{repo}", "vcs")
                    _write(f"source-id-{variant}", f"vcs-{ref}")
                    _write(f"build-id-{variant}", self.vcs_build_id("vcs"))

                if not os.path.exists(f"src{lnk}"):
                    impl = registry.get(name)
                    if impl is not None and impl.names[0] == "svn":
                        #  svn-branch "" "" $module $ref "": messages to the console
                        with open(os.devnull, "w") as null:
                            r = Run(self.d.base_env(), self.get("SCBI_BDIR"), null, self.d.log)
                            impl.link_src(r, module, ref)
                    else:
                        self._ln("vcs", "src")

                _write("source-ref", f"{module} ")
                _write("source-ref", self.vcs_ref(name, ref, f"{os.getcwd()}/vcs"), "a")
                shutil.copyfile(f"source-id-{variant}", "source-id")
                return 0
            hassrc = "no"

        if hassrc == "no":
            _write(f"source-id-{variant}", f"none-{ref}")
            shutil.copyfile(f"source-id-{variant}", "source-id")
            _write("source-ref", f"{module} none {variant} revision {ref}\n", "a")
            if not os.path.isdir("src"):
                self.ilog(module, "no sources (vcs or tar)")
                _write(f"build-id-{variant}", self.build_id(variant))
            else:
                _write(f"build-id-{variant}", self.build_id(self.epoch()))
        return 0

    def _ln(self, target: str, name: str) -> int:
        """``ln -s TARGET NAME`` (errors to the console)."""
        import subprocess

        proc = subprocess.run(["ln", "-s", target, name], capture_output=True, text=True)
        for line in (proc.stdout + proc.stderr).splitlines():
            self.out(line)
        return proc.returncode


class _Null:
    def write(self, text: str) -> None:
        pass

    def flush(self) -> None:
        pass


_NULL = _Null()


def handle_sources(builder, formodule: str, modref: str) -> int:
    return Sources(builder, formodule, modref).handle()


def _rm_f(path: str) -> None:
    try:
        if not (os.path.isdir(path) and not os.path.islink(path)):
            os.unlink(path)
    except OSError:
        pass


def _rm_rf(path: str) -> None:
    if os.path.islink(path) or os.path.isfile(path):
        os.unlink(path)
    elif os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
