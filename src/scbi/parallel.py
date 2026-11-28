"""--parallel: the modules of a build handled by several driver processes.

The main process computes the graph of the modules of the build (the
walk of handle_module / handle_depends: dependencies, build dependencies,
tests dependencies with --tests, modules of the meta-modules) and starts
a worker for each module whose dependencies are done, up to K at a time.

A worker is a run of the driver (``python -m scbi``) with the options of
the main run and the module as its only module, in the worker mode
(SCBI_PARALLEL_WORKER):

- it uses the build plan of the main process (SCBI_PLAN_STATE), not
  recomputed;
- it only builds its module: the dependencies and the modules of a
  meta-module are done, it only records their build ids
  (build-deps-<variant>, as a sequential build does);
- its build and tests steps wait for a build slot (SCBI_BUILD_SLOTS, 1 by
  default: one heavy step at a time); two testsuites never run at the
  same time; the global installs and the host builds are serialized;
- its output goes to the main process, which prints it as one block when
  the module ends. Lines starting with STATUS_MARK give the step in
  progress (shown in the status bar, not printed).

Two modules sharing their directory in the sandbox (two variants) or
their VCS checkout are never handled at the same time. On a failure no
new module is started, the running ones finish, the run fails.

Not handled in parallel (the build is sequential, with a message): a
meta-module with a plan or an aggregate hook, a build without --deps,
--dry-run, a global install directory not writable (sudo), a platform
without FIFO.
"""

from __future__ import annotations

import contextlib
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from scbi.errors import Exit
from scbi.plugin.resolve import get_hook

try:
    import fcntl
except ImportError:  # pragma: no cover - not on Windows
    fcntl = None  # type: ignore[assignment]

WORKER_ENV = "SCBI_PARALLEL_WORKER"
STATE_ENV = "SCBI_PLAN_STATE"
SLOTS_ENV = "SCBI_BUILD_SLOTS_FIFO"
#  a status line of a worker (not part of its output)
STATUS_MARK = "\x1escbi-status "

DEFAULT_MODULES = 2
#  the steps waiting for a build slot
HEAVY_STEPS = ("build", "tests")

#  options of the main run not given to the workers (handled by the main
#  process, or meaningless for one module)
_DROPPED = ("--parallel", "--clear-cache", "--dry-run", "--standalone", "--stat", "--progress")
#  options followed by their value as a separate argument
_WITH_VALUE = ("-e", "-t", "-j", "--jobs", "--prefix", "--env", "--build-target", "--list-plan")


class Unsupported(Exception):
    """The build cannot be done in parallel (the reason)."""


# ------------------------------------------------------------ the worker


def is_worker(driver) -> bool:
    return driver.environ.get(WORKER_ENV) == "yes"


def status(text: str) -> None:
    """A status line of a worker for the main process."""
    sys.stdout.write(f"{STATUS_MARK}{text}\n")
    sys.stdout.flush()


@contextlib.contextmanager
def file_lock(path: str):
    """An exclusive lock on ``path`` (nothing without fcntl)."""
    if fcntl is None:
        yield
        return
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextlib.contextmanager
def heavy_step(driver, step: str):
    """In a worker, a build or tests step holds a build slot (and the tests
    lock); nothing otherwise."""
    fifo = driver.environ.get(SLOTS_ENV, "")
    if not is_worker(driver):
        yield
        return
    if step not in HEAVY_STEPS or not fifo:
        status(step)
        yield
        return
    status(f"{step} (waiting)")
    with contextlib.ExitStack() as stack:
        if step == "tests":
            stack.enter_context(file_lock(os.path.join(driver.get("SCBI_BDIR"), ".tests.lock")))
        fd = os.open(fifo, os.O_RDWR)
        try:
            token = os.read(fd, 1)
            status("@slot+")
            status(step)
            try:
                yield
            finally:
                os.write(fd, token or b"+")
                status("@slot-")
        finally:
            os.close(fd)


def load_state(driver, path: str) -> None:
    """The build plan of the main process."""
    data = json.loads(Path(path).read_text())
    driver.plan.modver.clear()
    driver.plan.modver.update(data["modver"])
    driver.plan.plan_hist.update(data.get("hist", {}))
    driver.plan.module_alias.update(data.get("alias", {}))


# -------------------------------------------------------------- the graph


@dataclass
class Job:
    key: str
    module: str
    variant: str
    #  the module reference given to the worker
    modref: str
    order: int = 0
    deps: set[str] = field(default_factory=set)
    resources: set[str] = field(default_factory=set)
    state: str = "waiting"  # waiting, running, done, failed, cancelled


def _repo(builder, module: str, variant: str) -> str:
    from scbi.sources.data import vcs_data

    data, rc = vcs_data(builder, module, variant)
    if rc != 0 or len(data) < 5 or data[3].upper() == "NONE":
        return ""
    url = data[4].rstrip("/")
    name = url.rsplit("/", 1)[-1]
    return name[:-len(".git")] if name.endswith(".git") else name


def build_graph(driver, builder) -> list[Job]:
    """The modules of the build in the order of a sequential build (the
    dependencies first)."""
    from scbi.tools.planwalk import format_ref

    plan, reg = driver.plan, driver.registry
    prefix, target = driver.get("SCBI_PREFIX"), driver.get("SCBI_TARGET")
    jobs: dict[str, Job] = {}
    active: set[str] = set()
    order: list[str] = []

    def visit(formodule: str, modref: str) -> str | None:
        info = plan.module_ref(modref, formodule)
        if len(info) > 4:
            raise Unsupported(f"{info[0]}: {' '.join(info[4:])}")
        module, variant, kind, ref = (info + [""] * 4)[:4]
        if ref == "skip" or reg.plugin_file(module) is None or builder.is_host_dep(modref):
            return None
        key = f"{module}+{variant}+{ref}"
        if key in jobs:
            return key
        if key in active:
            raise Unsupported(f"{module}: recursive dependencies")
        builder.load_module(module, variant)
        parent = "@root" if formodule == "@root" else formodule.split(":", 1)[0].split("/", 1)[0]
        if parent != "@root" and builder.is_hook_true(module, variant, "only-explicit-build", "FALSE"):
            return None
        active.add(key)
        fkey = f"{parent}={module}"
        if plan.modver.get(fkey):
            wref = format_ref(module, variant, kind, ref[len("keep:"):] if ref.startswith("keep:") else ref)
        else:
            wref = module
        job = Job(key, module, variant, wref)
        job.resources.add(f"module:{module}")
        repo = _repo(builder, module, variant)
        if repo:
            job.resources.add(f"repo:{repo}")
        deps: set[str] = set()
        cross = driver.runner().cross
        if reg.loaded.get(f"{module}.{variant}") == "meta":
            for hook in ("plan", "aggregate"):
                if get_hook(reg, module, variant, hook, cross):
                    raise Unsupported(f"meta-module {module} ({hook} hook)")
            for dmodule in builder.get_all_depends(module, variant, "build-depends"):
                deps.add(visit(module, dmodule) or "")
            mods = driver.runner().variant_values(module, variant, "modules", [prefix, target, variant],
                                                  plan, builder.modules_list)
            from scbi.bashcompat import words

            for m in words("\n".join(mods)):
                deps.add(visit(module, m) or "")
        else:
            hooks = ["build-depends", "depends"] + (["tests-depends"] if driver.get("DO_TEST") != "no" else [])
            for hook in hooks:
                for dmodule in builder.get_all_depends(module, variant, hook):
                    deps.add(visit(modref, dmodule) or "")
        deps.discard("")
        deps.discard(key)
        job.deps = deps
        active.discard(key)
        jobs[key] = job
        job.order = len(order)
        order.append(key)
        return key

    for m in driver.modules:
        visit("@root", m)
    return [jobs[k] for k in order]


# ----------------------------------------------------------- the workers


def worker_args(driver, modref: str) -> list[str]:
    """The options of the main run, without its modules, for a worker."""
    args: list[str] = []
    raw = list(getattr(driver, "raw_args", []))
    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--":
            break
        if a in _WITH_VALUE:
            args += raw[i:i + 2]
            i += 2
            continue
        if a.startswith("-"):
            if a.startswith(_DROPPED):
                pass
            elif a == "--update:prefetch":
                args.append("--update")
            else:
                args.append(a)
        i += 1
    return [*args, "--progress:no", modref]


@dataclass
class Worker:
    job: Job
    proc: subprocess.Popen
    output: list[str] = field(default_factory=list)
    partial: bytes = b""
    step: str = "starting"
    slot: bool = False
    start: float = 0.0


class Scheduler:
    def __init__(self, driver, jobs: list[Job], width: int, slots: int):
        self.d = driver
        self.jobs = {j.key: j for j in jobs}
        self.order = jobs
        self.width = max(width, 1)
        self.slots = max(slots, 1)
        self.running: dict[int, Worker] = {}
        self.failed = False
        self.sel = selectors.DefaultSelector()
        self.tmp = tempfile.mkdtemp(prefix="scbi-parallel-", dir=self._tmpdir())
        self.fifo = os.path.join(self.tmp, "slots")
        self.state = os.path.join(self.tmp, "plan.json")

    def _tmpdir(self) -> str:
        bdir = self.d.get("SCBI_BDIR")
        path = os.path.join(bdir, ".cache")
        os.makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------ setup

    def prepare(self) -> None:
        plan = self.d.plan
        Path(self.state).write_text(json.dumps({"modver": plan.modver, "hist": plan.plan_hist,
                                                "alias": plan.module_alias}))
        os.mkfifo(self.fifo)
        #  kept open by the main process: the tokens stay in the FIFO
        self.fifo_fd = os.open(self.fifo, os.O_RDWR | os.O_NONBLOCK)
        os.write(self.fifo_fd, b"+" * self.slots)

    def cleanup(self) -> None:
        for w in self.running.values():
            with contextlib.suppress(OSError):
                w.proc.kill()
        with contextlib.suppress(OSError):
            os.close(self.fifo_fd)
        for p in (self.fifo, self.state):
            with contextlib.suppress(OSError):
                os.unlink(p)
        with contextlib.suppress(OSError):
            os.rmdir(self.tmp)

    # --------------------------------------------------------- workers

    def env(self) -> dict[str, str]:
        import scbi

        env = dict(self.d.environ)
        #  the progress is the one of the main process
        env.pop("SCBI_TEST_PROGRESS", None)
        pkg = str(Path(scbi.__file__).resolve().parent.parent)
        env["PYTHONPATH"] = pkg + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
        env.update({"SCBI_NESTED": "yes", WORKER_ENV: "yes", STATE_ENV: self.state, SLOTS_ENV: self.fifo,
                    "SCBI_RUN_ID": self.d.get("SCBI_RUN_ID"), "PYTHONUNBUFFERED": "1"})
        return env

    def launch(self, job: Job) -> None:
        args = [sys.executable, "-m", "scbi", *worker_args(self.d, job.modref)]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, cwd=getattr(self.d, "start_cwd", os.getcwd()),
                                env=self.env())
        assert proc.stdout is not None
        os.set_blocking(proc.stdout.fileno(), False)
        w = Worker(job, proc, start=time.monotonic())
        self.running[proc.stdout.fileno()] = w
        self.sel.register(proc.stdout, selectors.EVENT_READ, w)
        job.state = "running"
        name = job.module if job.variant == "default" else f"{job.module}/{job.variant}"
        progress = getattr(self.d, "progress", None)
        if progress is not None:
            progress.next(name)
        self.show()

    def ready(self) -> list[Job]:
        busy = {r for w in self.running.values() for r in w.job.resources}
        out = []
        for job in self.order:
            if job.state != "waiting":
                continue
            if any(self.jobs[k].state != "done" for k in job.deps if k in self.jobs):
                continue
            if job.resources & busy:
                continue
            out.append(job)
            busy |= job.resources
        return out

    def read(self, w: Worker) -> bool:
        """Reads the output of a worker; False at its end."""
        assert w.proc.stdout is not None
        try:
            data = os.read(w.proc.stdout.fileno(), 65536)
        except BlockingIOError:
            return True
        if not data:
            if w.partial:
                self._line(w, w.partial.decode(errors="surrogateescape"))
                w.partial = b""
            return False
        data = w.partial + data
        *lines, w.partial = data.split(b"\n")
        for line in lines:
            self._line(w, line.decode(errors="surrogateescape"))
        return True

    def _line(self, w: Worker, line: str) -> None:
        if line.startswith(STATUS_MARK):
            text = line[len(STATUS_MARK):]
            if text == "@slot+":
                w.slot = True
            elif text == "@slot-":
                w.slot = False
            else:
                w.step = text
                self.show()
            return
        w.output.append(line)

    def finish(self, w: Worker) -> None:
        assert w.proc.stdout is not None
        self.sel.unregister(w.proc.stdout)
        del self.running[w.proc.stdout.fileno()]
        rc = w.proc.wait()
        w.proc.stdout.close()
        if w.slot:
            #  ended holding a slot (killed): the token is given back
            with contextlib.suppress(OSError):
                os.write(self.fifo_fd, b"+")
        w.job.state = "done" if rc == 0 else "failed"
        if rc != 0:
            self.failed = True
        self.print_block(w.output)
        self.show()

    def print_block(self, lines: list[str]) -> None:
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines:
            sys.stdout.write("\n".join(lines) + "\n\n")
            sys.stdout.flush()

    def show(self) -> None:
        """The modules in progress in the status bar."""
        progress = getattr(self.d, "progress", None)
        st = getattr(progress, "status", None)
        #  not with the progress lines of the testsuite (one per module)
        if st is None or type(st).__name__ == "Lines":
            return
        done = sum(1 for j in self.order if j.state in ("done", "failed"))
        parts = [f"{w.job.module}: {w.step}" for w in self.running.values()]
        st.set(f"[{done}/{len(self.order)}] " + " · ".join(parts))

    # ------------------------------------------------------------- run

    def run(self) -> bool:
        """Handles all the jobs; False when one failed."""
        self.prepare()
        try:
            while True:
                if not self.failed:
                    for job in self.ready():
                        if len(self.running) >= self.width:
                            break
                        self.launch(job)
                if not self.running:
                    break
                for key, _ in self.sel.select(timeout=1.0):
                    w = key.data
                    if not self.read(w):
                        self.finish(w)
        finally:
            self.cleanup()
        for job in self.order:
            if job.state == "waiting":
                job.state = "cancelled"
        return not self.failed


# ------------------------------------------------------------ the driver


def width(driver) -> int:
    """K, the number of modules handled at the same time (0: not
    parallel)."""
    value = driver.get("DO_PARALLEL")
    if not value or value == "no" or is_worker(driver):
        return 0
    if value == "yes":
        return DEFAULT_MODULES
    try:
        return int(value)
    except ValueError:
        return DEFAULT_MODULES


def run(driver, builder) -> bool:
    """Builds the modules of the run in parallel; False when the build must
    be done sequentially (the reason displayed)."""
    k = width(driver)
    if k < 2:
        return False
    reason = ""
    if driver.get("DEPS") != "yes":
        reason = "needs --deps"
    elif driver.get("DRY_RUN") == "yes":
        reason = "not with --dry-run"
    elif not hasattr(os, "mkfifo") or fcntl is None:
        reason = "not supported on this platform"
    else:
        prefix = driver.get("SCBI_PREFIX")
        probe = prefix
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        if probe and not os.access(probe, os.W_OK):
            reason = f"install directory {prefix} not writable"
    jobs: list[Job] = []
    if not reason:
        try:
            jobs = build_graph(driver, builder)
        except Unsupported as e:
            reason = str(e)
        except Exit:
            reason = "error in the dependencies"
    if reason:
        driver.log.ilog("build", f"parallel build: {reason}, building sequentially")
        return False
    try:
        slots = int(driver.get("SCBI_BUILD_SLOTS") or "1")
    except ValueError:
        slots = 1
    driver.log.ilog("build", f"parallel build: {len(jobs)} module(s), {k} at a time, "
                             f"{slots} build slot(s)")
    driver.log.line_sep()
    if not Scheduler(driver, jobs, k, slots).run():
        raise Exit(1)
    return True
