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
meta-module with a plan hook, a build without --deps,
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
from scbi.log import StatusBar
from scbi.plugin.resolve import get_hook

try:
    import fcntl
except ImportError:  # pragma: no cover - not on Windows
    fcntl = None  # type: ignore[assignment]

WORKER_ENV = "SCBI_PARALLEL_WORKER"
STATE_ENV = "SCBI_PLAN_STATE"
SLOTS_ENV = "SCBI_BUILD_SLOTS_FIFO"
#  the modules needing the module of a worker, as a sequential build
#  displays them (needed by:)
NEEDED_BY_ENV = "SCBI_NEEDED_BY"
#  the depends kind and the aggregate mode of the module of a worker, as a
#  sequential build gives them (the final step)
KIND_ENV = "SCBI_DEPENDS_KIND"


def worker_kind(driver) -> tuple[str, str]:
    """(depends kind, is aggregated) of the module of a worker."""
    value = driver.environ.get(KIND_ENV, "") if is_worker(driver) else ""
    kind, _, agg = value.partition(" ")
    return kind or "default", agg or "no"
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
    #  the modules being handled when the walk reached it, the root first
    #  (Builder.modules_list in a sequential build)
    needed_by: list[str] = field(default_factory=list)
    #  as in a sequential build (the final step of the module)
    depends_kind: str = "default"
    is_aggregated: str = "no"
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
    #  the modules being visited (Builder.modules_list)
    stack: list[str] = []

    def visit(formodule: str, modref: str, kind_of_dep: str = "default", is_aggregated: str = "no") -> str | None:
        """``kind_of_dep``, ``is_aggregated``: as given to handle_module by a
        sequential build (the depends kind, the aggregate mode of the
        meta-module aggregating it), for the worker (final step)."""
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
        job = Job(key, module, variant, wref, needed_by=list(stack), depends_kind=kind_of_dep,
                  is_aggregated=is_aggregated)
        stack.append(module if variant == "default" else f"{module}/{variant}")
        job.resources.add(f"module:{module}")
        repo = _repo(builder, module, variant)
        if repo:
            job.resources.add(f"repo:{repo}")
        deps: set[str] = set()
        cross = driver.runner().cross
        if reg.loaded.get(f"{module}.{variant}") == "meta":
            if get_hook(reg, module, variant, "plan", cross):
                #  its modules are resolved with another build plan
                raise Unsupported(f"meta-module {module} (plan hook)")
            #  an aggregate: built after its modules (its wrapup copies their
            #  installations), as the other meta-modules (handle_meta_module)
            agg_mode = "no"
            if get_hook(reg, module, variant, "aggregate", cross):
                agg_mode = driver.runner().hook_value(
                    module, variant, "aggregate", [prefix, driver.get("TARGET"), variant], plan,
                    builder.modules_list) or ""
            for dmodule in builder.get_all_depends(module, variant, "build-depends"):
                deps.add(visit(module, dmodule, "build", "no") or "")
            mods = driver.runner().variant_values(module, variant, "modules", [prefix, target, variant],
                                                  plan, builder.modules_list)
            from scbi.bashcompat import words

            for m in words("\n".join(mods)):
                deps.add(visit(module, m, "default", agg_mode) or "")
        else:
            #  handle_all_depends: in a direct aggregate, the dependencies of
            #  its modules are not aggregated
            dep_agg = "no" if is_aggregated == "direct" else is_aggregated
            hooks = [("build-depends", "build"), ("depends", "default")]
            if driver.get("DO_TEST") != "no":
                hooks.append(("tests-depends", "tests"))
            for hook, dkind in hooks:
                for dmodule in builder.get_all_depends(module, variant, hook):
                    deps.add(visit(modref, dmodule, dkind, dep_agg) or "")
        stack.pop()
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
    #  waiting for a build slot since
    waiting: float = 0.0


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
        #  what the build did: the time with n modules running, with a free
        #  place but no module ready (dependencies), waiting for a slot
        self.t0 = self.last = time.monotonic()
        self.running_time: dict[int, float] = {}
        self.cur_running = 0
        self.cur_blocked = False
        self.blocked_time = 0.0
        self.slot_wait = 0.0
        self.timeline = None

    def _tmpdir(self) -> str:
        bdir = self.d.get("SCBI_BDIR")
        path = os.path.join(bdir, ".cache")
        os.makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------ setup

    def prepare(self) -> None:
        d = self.d
        path = os.path.join(d.get("SCBI_LOGS"), d.get("TODAY"), f"{d.get('SCBI_TARGET')}-parallel.log")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self.timeline = open(path, "w")
            self.timeline_path = path
            self.timeline.write(f"# run {d.get('SCBI_RUN_ID')}: {len(self.order)} module(s), {self.width} at a time,"
                                f" {self.slots} build slot(s)\n")
        except OSError:
            self.timeline = None
        plan = self.d.plan
        Path(self.state).write_text(json.dumps({"modver": plan.modver, "hist": plan.plan_hist,
                                                "alias": plan.module_alias}))
        os.mkfifo(self.fifo)
        #  kept open by the main process: the tokens stay in the FIFO
        self.fifo_fd = os.open(self.fifo, os.O_RDWR | os.O_NONBLOCK)
        os.write(self.fifo_fd, b"+" * self.slots)

    def event(self, w: "Worker | None", text: str) -> None:
        """A line of the timeline: the time since the start, the module."""
        if self.timeline is not None:
            name = "" if w is None else (w.job.module if w.job.variant == "default"
                                         else f"{w.job.module}/{w.job.variant}")
            self.timeline.write(f"{time.monotonic() - self.t0:9.1f}  {name:<30} {text}\n")
            self.timeline.flush()

    def tick(self) -> None:
        """The time since the last change, accounted to the state the build
        was in; then the new state."""
        now = time.monotonic()
        dt = now - self.last
        self.last = now
        self.running_time[self.cur_running] = self.running_time.get(self.cur_running, 0.0) + dt
        if self.cur_blocked:
            self.blocked_time += dt
        self.cur_running = len(self.running)
        self.cur_blocked = (not self.failed and len(self.running) < self.width
                            and any(j.state == "waiting" for j in self.order))

    def summary(self) -> list[str]:
        """What the parallel build did, for the user."""
        total = time.monotonic() - self.t0

        def hms(sec: float) -> str:
            sec = int(round(sec))
            return f"{sec // 3600}:{sec // 60 % 60:02d}:{sec % 60:02d}"

        def pct(sec: float) -> str:
            #  %%: the messages of the driver are printf formats
            return f"{100 * sec / total:.0f}%%" if total > 0 else "0%%"

        counts = ", ".join(f"{n} {'module' if n == 1 else 'modules'} {pct(t)}"
                           for n, t in sorted(self.running_time.items()) if n > 0 and t > 0)
        lines = [f"parallel build finished in {hms(total)}, {len(self.order)} module(s)",
                 f"  running: {counts or 'none'} of the time",
                 f"  a free place, the modules waiting for their dependencies: {hms(self.blocked_time)}"
                 f" ({pct(self.blocked_time)})",
                 f"  build and tests steps waiting for a build slot (SCBI_BUILD_SLOTS={self.slots}):"
                 f" {hms(self.slot_wait)}"]
        if self.timeline is not None:
            lines.append(f"  timeline: {self.timeline_path}")
        return lines

    def cleanup(self) -> None:
        for w in self.running.values():
            with contextlib.suppress(OSError):
                w.proc.kill()
        with contextlib.suppress(OSError):
            os.close(self.fifo_fd)
        for p in (self.fifo, self.state):
            with contextlib.suppress(OSError):
                os.unlink(p)
        if self.timeline is not None:
            self.event(None, "end")
            self.timeline.close()
        with contextlib.suppress(OSError):
            os.rmdir(self.tmp)

    # --------------------------------------------------------- workers

    def env(self, job: Job) -> dict[str, str]:
        import scbi

        env = dict(self.d.environ)
        #  the progress is the one of the main process
        env.pop("SCBI_TEST_PROGRESS", None)
        pkg = str(Path(scbi.__file__).resolve().parent.parent)
        env["PYTHONPATH"] = pkg + (f":{env['PYTHONPATH']}" if env.get("PYTHONPATH") else "")
        env.update({"SCBI_NESTED": "yes", WORKER_ENV: "yes", STATE_ENV: self.state, SLOTS_ENV: self.fifo,
                    "SCBI_RUN_ID": self.d.get("SCBI_RUN_ID"), "PYTHONUNBUFFERED": "1",
                    NEEDED_BY_ENV: " ".join(job.needed_by),
                    KIND_ENV: f"{job.depends_kind} {job.is_aggregated}"})
        #  the purge@ modules of the run
        env.pop("SCBI_PURGE_MODULES", None)
        if self.d.purge_modules:
            env["SCBI_PURGE_MODULES"] = self.d.purge_modules_env()
        return env

    def launch(self, job: Job) -> None:
        args = [sys.executable, "-m", "scbi", *worker_args(self.d, job.modref)]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, cwd=getattr(self.d, "start_cwd", os.getcwd()),
                                env=self.env(job))
        assert proc.stdout is not None
        os.set_blocking(proc.stdout.fileno(), False)
        w = Worker(job, proc, start=time.monotonic())
        self.running[proc.stdout.fileno()] = w
        self.sel.register(proc.stdout, selectors.EVENT_READ, w)
        job.state = "running"
        name = job.module if job.variant == "default" else f"{job.module}/{job.variant}"
        progress = getattr(self.d, "progress", None)
        #  the progress lines of the testsuite: one per module started (the
        #  status bar shows the modules running, show())
        if progress is not None and type(getattr(progress, "status", None)).__name__ == "Lines":
            progress.next(name)
        self.event(w, "start")
        self.tick()
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
            now = time.monotonic()
            if text == "@slot+":
                w.slot = True
                if w.waiting:
                    self.slot_wait += now - w.waiting
                    w.waiting = 0.0
                self.event(w, "build slot taken")
            elif text == "@slot-":
                w.slot = False
                self.event(w, "build slot given back")
            else:
                w.step = text
                if text.endswith("(waiting)"):
                    w.waiting = now
                self.event(w, text)
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
        self.event(w, w.job.state)
        self.tick()
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
        items = [(w.job.module, w.step) for w in self.running.values()]
        prefix = f"[{done}/{len(self.order)}] "
        if not isinstance(st, StatusBar):
            #  the line mode: no room limit, no spinner
            st.set(fit_status(prefix, items, 0))
            return
        #  the room of the text on the status bar (the elapsed time on the
        #  right), the spinner animated by the bar
        room = st.room()
        spinner = st.spinner()
        st.set(lambda frame: fit_status(prefix, items, room, frame, spinner))

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
                self.tick()
                for key, _ in self.sel.select(timeout=1.0):
                    w = key.data
                    if not self.read(w):
                        self.finish(w)
            self.tick()
        finally:
            self.cleanup()
        for job in self.order:
            if job.state == "waiting":
                job.state = "cancelled"
        return not self.failed


#  the steps in the status bar: one letter
STEP_CODES = {"setup": "S", "config": "C", "build": "B", "install": "I", "tests": "T", "wrapup": "W"}


def fit_status(prefix: str, items: list[tuple[str, str]], room: int,
               frame: int | None = None, spinner: str = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏") -> str:
    """The modules running and their step on one line of ``room``
    characters (0: no limit): all of them are shown, the names shortened
    when needed. A step is its letter (STEP_CODES) then a mark: … waiting
    for a build slot, otherwise the frame ``frame`` of ``spinner`` (a
    space without frame). The width does not depend on the frame."""
    sep = "  "

    def step(s: str) -> str:
        waiting = s.endswith("(waiting)")
        s = s[:-len("(waiting)")].strip() if waiting else s
        if waiting:
            mark = "…"
        elif frame is None or not spinner:
            mark = " "
        else:
            mark = spinner[frame % len(spinner)]
        return STEP_CODES.get(s, s) + mark

    def line(parts: list[str]) -> str:
        return (prefix + sep.join(parts)).rstrip()

    #  a prefix common to all the names (c-...) dropped
    names = [m for m, _ in items]
    common = os.path.commonprefix(names)
    common = common[:common.rfind("-") + 1] if "-" in common else ""
    if common and all(len(m) > len(common) for m in names):
        names = [m[len(common):] for m in names]
    steps = [step(s) for _, s in items]
    full = line([f"{m}:{s}" for m, s in zip(names, steps)])
    if room <= 0 or len(full) <= room or not items:
        return full
    #  the names shortened, the same room for each module
    each = (room - len(prefix) - len(sep) * (len(items) - 1)) // len(items)
    parts = []
    for m, s in zip(names, steps):
        keep = max(each - len(s) - 1, 3)
        name = m if len(m) <= keep else m[:keep - 1] + "…"
        parts.append(f"{name}:{s}")
    return line(parts)


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
        #  repeated at the end of the build (scbi.driver)
        driver.parallel_fallback = reason
        return False
    try:
        slots = int(driver.get("SCBI_BUILD_SLOTS") or "1")
    except ValueError:
        slots = 1
    driver.log.ilog("build", f"parallel build: {len(jobs)} module(s), {k} at a time, "
                             f"{slots} build slot(s)")
    driver.log.line_sep()
    scheduler = Scheduler(driver, jobs, k, slots)
    ok = scheduler.run()
    for line in scheduler.summary():
        driver.log.ilog("build", line)
    if not ok:
        raise Exit(1)
    return True
