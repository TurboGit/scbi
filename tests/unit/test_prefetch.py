"""--update:prefetch: the jobs and their results (scbi.sources.prefetch),
on local git repositories."""

import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from scbi.log import Logger
from scbi.sources import prefetch
from scbi.sources.prefetch import Prefetcher, _Closed

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_NOSYSTEM": "1", "HOME": "/nonexistent"}


def git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


def commit(repo: Path, text: str) -> str:
    (repo / "v.txt").write_text(text)
    git(repo, "add", "v.txt")
    git(repo, "commit", "-q", "-m", text)
    return git(repo, "rev-parse", "HEAD")


class FakeDriver:
    def __init__(self, tmp: Path):
        self.values = {"SCBI_BDIR": str(tmp / "builds"), "SCBI_ARCHIVES": str(tmp / "archives")}
        self.log = Logger(tmp / "logs", "today", "tgt", Path(os.devnull))

    def get(self, name):
        return self.values.get(name, "")


class FakeBuilder:
    def __init__(self, tmp: Path):
        self.d = FakeDriver(tmp)


@pytest.fixture
def origin(tmp_path):
    repo = tmp_path / "origin" / "repo"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    commit(repo, "v1")
    return repo


def submit(p: Prefetcher, url: str):
    path = p.git_path("", url)
    log, _ = p._paths(path)
    p.jobs[path] = p.pool.submit(p._git_job, GIT_ENV, url, "", path, log)
    return path


def test_git_job_clone_then_fetch(tmp_path, origin):
    p = Prefetcher(FakeBuilder(tmp_path), jobs=2)
    url = str(origin)
    module_log = tmp_path / "module.log"
    try:
        #  a new clone
        path = submit(p, url)
        res = p.vcs_result("", url, str(module_log))
        assert res is not None and res.ok
        assert os.path.isdir(f"{path}/.git")
        #  a new commit in the remote: fetched by the job of the next run
        head = commit(origin, "v2")
        submit(p, url)
        assert p.vcs_result("", url, str(module_log)) is not None
        assert git(path, "rev-parse", "origin/main") == head
        #  another URL for the same clone, an unknown clone: no result
        assert p.vcs_result("", url + "-other", str(module_log)) is None
        assert p.vcs_result("nothere", url, str(module_log)) is None
    finally:
        p.shutdown()
    #  the scratch directory of the jobs removed
    assert not os.path.exists(p.dir)


def test_git_job_failure(tmp_path):
    p = Prefetcher(FakeBuilder(tmp_path), jobs=1)
    try:
        url = str(tmp_path / "does-not-exist")
        submit(p, url)
        #  a failure: no result (the main loop updates and reports the error)
        assert p.vcs_result("", url, str(tmp_path / "m.log")) is None
    finally:
        p.shutdown()


def test_shutdown_terminates_the_commands(tmp_path):
    p = Prefetcher(FakeBuilder(tmp_path), jobs=1)
    started = threading.Event()

    def job():
        started.set()
        return p.procs.run(["sleep", "30"])

    future = p.pool.submit(job)
    queued = p.pool.submit(lambda: "never")
    started.wait(5)
    time.sleep(0.2)
    t0 = time.monotonic()
    p.shutdown()
    assert time.monotonic() - t0 < 10
    assert future.result()[0] != 0  # terminated
    assert queued.cancelled()
    with pytest.raises(_Closed):
        p.procs.run(["true"])


def test_batch_env():
    env = prefetch._batch_env({"PATH": "/bin"})
    assert env["GIT_TERMINAL_PROMPT"] == "0" and "BatchMode=yes" in env["GIT_SSH_COMMAND"]
    #  an ssh command of the user kept
    assert prefetch._batch_env({"GIT_SSH_COMMAND": "myssh"})["GIT_SSH_COMMAND"] == "myssh"
