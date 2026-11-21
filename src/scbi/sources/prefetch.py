"""--update:prefetch: the network part of the update of the sources done
ahead, in parallel, while the modules before are built.

For each module of the build (in build order) a job, run by a pool of
threads, updates its git clone (``git fetch``, or the clone) or downloads
its archive in the archive store, as the main loop would, and records
the result. When the main loop reaches the module (scbi.sources.handle),
it waits for the job of its clone or archive and, when the job succeeded
for the same URL, only does the local part (switch to the reference,
extraction): nothing is fetched again. Without a result (no job, another
URL, a failure) the main loop does the update as without prefetch, with
its usual messages and errors.

The threads only run commands: the hooks (vcs, archive) and the
environment of the commands are evaluated in the main thread, before a
job is submitted. A job is never prompted (GIT_TERMINAL_PROMPT=0, ssh in
batch mode): a repository needing a password is updated by the main
loop. Only git and the archives are prefetched (svn update changes the
working copy).
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import shutil
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from scbi.sources.archive.fetch import _download, check_tool
from scbi.sources.data import archive_data, archive_exists, vcs_data
from scbi.sources.run import Run, command_env
from scbi.sources.vcs import registry
from scbi.sources.vcs.base import option_list
from scbi.sources.vcs.git import _basename, set_submodule_url

DEFAULT_JOBS = 4


class _Closed(Exception):
    """The prefetcher is shut down: no new command."""


class _Procs:
    """The commands running in the jobs, terminated by the shutdown."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running: set[subprocess.Popen] = set()
        self.closed = False

    def run(self, args: list[str], *, input_: bytes | None = None, **kw) -> tuple[int, bytes]:
        with self.lock:
            if self.closed:
                raise _Closed()
            p = subprocess.Popen(args, **kw)
            self.running.add(p)
        try:
            out, _ = p.communicate(input_)
        finally:
            with self.lock:
                self.running.discard(p)
        return p.returncode, out or b""

    def close(self) -> None:
        with self.lock:
            self.closed = True
            procs = list(self.running)
        for p in procs:
            #  SIGTERM: git removes its lock files
            p.terminate()


@dataclass
class _JobRun(Run):
    """scbi.sources.run.Run with its commands tracked (shutdown)."""

    procs: _Procs = field(default_factory=_Procs)

    def run(self, *args: str) -> int:
        self.log.flush()
        try:
            rc, _ = self.procs.run(list(args), cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
                                   stdout=self.log, stderr=subprocess.STDOUT)
            return rc
        except FileNotFoundError:
            self.log.write(f"bash: {args[0]}: command not found\n")
            self.log.flush()
            return 127

    def output(self, *args: str) -> tuple[int, str]:
        self.log.flush()
        try:
            rc, out = self.procs.run(list(args), cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=self.log)
        except FileNotFoundError:
            self.log.write(f"bash: {args[0]}: command not found\n")
            self.log.flush()
            return 127, ""
        return rc, out.decode(errors="surrogateescape").rstrip("\n")


class _JobIo:
    """The ``io`` of fetch._download with its commands tracked."""

    def __init__(self, log: str, env: dict[str, str], procs: _Procs):
        self.log = log
        self.env = env
        self.procs = procs

    def run(self, args: list[str], cwd: str, stdout_to_stderr: bool = False) -> int:
        with open(self.log, "a") as f:
            try:
                rc, _ = self.procs.run(args, cwd=cwd, env=self.env, stdin=subprocess.DEVNULL,
                                       stdout=f, stderr=subprocess.STDOUT)
                return rc
            except FileNotFoundError:
                f.write(f"bash: {args[0]}: command not found\n")
                return 127


@dataclass
class Result:
    """The result of a job: ``ok``, the URL used, the log of its commands
    and, for an archive, whether it was downloaded (1) or unchanged (0)."""

    ok: bool
    url: str
    log: str
    downloaded: int = 0


def _batch_env(env: dict[str, str]) -> dict[str, str]:
    """No prompt in a job (a password: the main loop asks for it)."""
    env = dict(env)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


class Prefetcher:
    """The jobs of the build, by resource: the clone ``$SCBI_BDIR/.vcs/<repo>``
    or the archive ``$SCBI_ARCHIVES/<file>`` (one job per resource: the
    modules or variants sharing one wait for the same job)."""

    def __init__(self, builder, jobs: int = DEFAULT_JOBS):
        self.b = builder
        self.d = builder.d
        self.bdir = self.d.get("SCBI_BDIR")
        self.archives = self.d.get("SCBI_ARCHIVES")
        self.dir = os.path.join(self.bdir, ".prefetch")
        os.makedirs(self.dir, exist_ok=True)
        self.pool = ThreadPoolExecutor(max_workers=max(jobs, 1), thread_name_prefix="scbi-prefetch")
        self.procs = _Procs()
        self.jobs: dict[str, Future] = {}

    # ---------------------------------------------------------- submit

    def start(self, planned) -> None:
        """Submit the jobs of the modules ``planned`` (formodule, module,
        variant, kind, ref), in build order."""
        for _formodule, module, variant, kind, ref in planned:
            if variant == "native" or kind == "DEV" or ref in ("skip", "keep"):
                continue
            try:
                if kind == "BRANCH" and self.d.get("ARCHIVE_CACHE") == "yes" \
                        and archive_exists(self.b, module, variant, ref):
                    kind = "VERSION"
                if kind == "VERSION":
                    self._archive(module, variant, ref)
                else:
                    self._git(module, variant)
            except Exception:  # noqa: BLE001 - a hook failing here: the main loop reports it
                continue

    def _paths(self, key: str) -> tuple[str, str]:
        """The log file and the temporary directory of the job of ``key``."""
        h = hashlib.md5(key.encode(errors="surrogateescape")).hexdigest()[:16]
        tmp = os.path.join(self.dir, h)
        os.makedirs(tmp, exist_ok=True)
        return os.path.join(self.dir, f"{h}.log"), tmp

    def _git(self, module: str, variant: str) -> None:
        vcs, _ = vcs_data(self.b, module, variant)
        if len(vcs) not in (5, 6):
            return
        proxy, options, name, url, dir = (vcs[1:6] + [""] * 5)[:5]
        impl = registry.get(name)
        if impl is None or impl.names[0] != "git" or url.upper() == "NONE":
            return
        path = self.git_path(dir, url)
        if path in self.jobs:
            return
        env = _batch_env(command_env(self.b, module, variant, proxy))
        log, _tmp = self._paths(path)
        self.jobs[path] = self.pool.submit(self._git_job, env, url, options, path, log)

    def _archive(self, module: str, variant: str, ref: str) -> None:
        tar, _ = archive_data(self.b, module, variant, ref)
        if len(tar) not in (6, 7):
            return
        proxy, taropts, tarcp, tarurl, tarsrc = tar[1:6]
        if "NONE" in (tarsrc.upper(), tarcp.upper(), tarurl.upper()):
            return
        path = f"{self.archives}/{tarsrc}"
        if path in self.jobs:
            return
        env = command_env(self.b, module, variant, proxy)
        if not check_tool(tarcp, env):
            return
        options = taropts.replace(",", " ", 1) if taropts.upper() != "NONE" else ""
        log, tmp = self._paths(path)
        self.jobs[path] = self.pool.submit(self._archive_job, env, tarcp, options, tarurl, tarsrc, log, tmp)

    def git_path(self, dir: str, url: str) -> str:
        """The clone of a vcs record (as Git.checkout)."""
        return f"{self.bdir}/.vcs/{dir or _basename(url, '.git')}"

    # ---------------------------------------------------------- jobs

    def _git_job(self, env: dict[str, str], url: str, options: str, path: str, log_path: str) -> Result:
        """Git.checkout without the link of the module: the clone, or the
        update of the existing clone (fetch); the tags of a new clone too."""
        recursive = "no-recursive" not in option_list(options)
        with open(log_path, "w") as log:
            #  the messages of the commands to the log of the job (as Run.to_log)
            logger = dataclasses.replace(self.d.log, stdout=log, stderr=log)
            r = _JobRun(env, self.bdir, log, logger, procs=self.procs)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            r.cwd = os.path.dirname(path)
            if not os.path.isdir(path):
                rc = r.run("git", "clone", url, os.path.basename(path))
                if rc == 0:
                    r.cwd = path
                    if os.path.isfile(os.path.join(path, ".gitmodules")):
                        set_submodule_url(r, options)
                        r.run("git", "submodule", "init")
                        rc = r.run("git", "submodule", "update", *(["--recursive"] if recursive else []))
            else:
                r.cwd = path
                if not os.path.isdir(os.path.join(path, ".git")):
                    return Result(False, url, log_path)
                r.run("git", "remote", "set-url", "origin", url)
                rc = 0
                if os.path.isfile(os.path.join(path, ".gitmodules")):
                    set_submodule_url(r, options)
                    rc = r.run("git", "submodule", "update", *(["--recursive"] if recursive else []))
            if rc == 0:
                rc = r.run("git", "fetch", "origin", "--force", "--tags",
                           *(["--recurse-submodules"] if recursive else []))
        return Result(rc == 0, url, log_path)

    def _archive_job(self, env: dict[str, str], tarcp: str, options: str, tarurl: str, tarsrc: str,
                     log_path: str, tmp: str) -> Result:
        """fetch._download into the archive store."""
        open(log_path, "w").close()
        io = _JobIo(log_path, env, self.procs)

        def elog(*msg: str) -> None:
            with open(log_path, "a") as f:
                f.write(" ".join(msg) + "\n")

        downloaded = _download(io, self.dir, tarcp, options, tarurl, tarsrc, self.archives, elog, tmp_dir=tmp)
        ok = os.path.isfile(f"{self.archives}/{tarsrc}")
        return Result(ok, tarurl, log_path, downloaded)

    # ---------------------------------------------------------- results

    def _result(self, path: str, url: str, log: str) -> Result | None:
        """Wait for the job of ``path`` (the main loop never works on a
        clone or an archive while its job runs); its result when it
        succeeded for ``url`` (its log appended to the module log ``log``),
        else None."""
        job = self.jobs.get(path)
        if job is None:
            return None
        try:
            res = job.result()
        except Exception:  # noqa: BLE001 - cancelled, a failure in the job: the main loop does it
            return None
        if not res.ok or res.url != url:
            return None
        try:
            with open(res.log, errors="surrogateescape") as src, open(log, "a") as dst:
                dst.write(src.read())
        except OSError:
            pass
        return res

    def vcs_result(self, dir: str, url: str, log: str) -> Result | None:
        return self._result(self.git_path(dir, url), url, log)

    def archive_result(self, path: str, url: str, log: str) -> Result | None:
        return self._result(path, url, log)

    def shutdown(self) -> None:
        """No more job; the running commands terminated (end of the
        build, failure, Ctrl-C)."""
        self.procs.close()
        self.pool.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(self.dir, ignore_errors=True)
