"""The wall and CPU time of the build steps.

Each step of a module (pre-, hook and post- parts together) appends a
line to ``$SCBI_LOGS/<day>/<target>-steps.log``:

    RUN  TIME  MODULE  VARIANT  STEP  WALL  CPU  JOBS  STATUS

tab-separated; RUN identifies the run of the driver (shared by its nested
runs), WALL and CPU are seconds, CPU the user and system time of the
commands of the step (-1 when not known), JOBS the value of SCBI_JOBS.
``scbi --stat:full`` summarizes the last run (scbi.log.display_step_stat):
how much of the build is spent in the steps using many cores (build,
tests) and how much of the CPU is used, to know what a parallel build of
independent modules could gain.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

try:
    import resource
except ImportError:  # pragma: no cover - not on Windows
    resource = None  # type: ignore[assignment]

#  the steps using many cores (make -j...)
HEAVY_STEPS = ("build", "tests")


def _cpu() -> float:
    if resource is None:
        return -1.0
    r = resource.getrusage(resource.RUSAGE_CHILDREN)
    return r.ru_utime + r.ru_stime


def start() -> tuple[float, float]:
    return time.monotonic(), _cpu()


def run_id(driver) -> str:
    """The identifier of the run, set once in the driver variables (a
    nested run of a host build gets it in its environment)."""
    rid = driver.get("SCBI_RUN_ID")
    if not rid:
        rid = f"{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}-{id(driver):x}"
        driver.set("SCBI_RUN_ID", rid, export=True)
    return rid


def record(driver, module: str, variant: str, step: str, begin: tuple[float, float], status: int) -> None:
    wall = time.monotonic() - begin[0]
    cpu1 = _cpu()
    cpu = cpu1 - begin[1] if cpu1 >= 0 and begin[1] >= 0 else -1.0
    path = Path(driver.get("SCBI_LOGS"), driver.get("TODAY"), f"{driver.get('SCBI_TARGET')}-steps.log")
    fields = [run_id(driver), time.strftime("%Y/%m/%d %H:%M:%S"), module, variant, step,
              f"{wall:.1f}", f"{cpu:.1f}", driver.get("SCBI_JOBS") or "1", str(status)]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        #  one write of a short line: atomic with several writers
        with open(path, "a") as f:
            f.write("\t".join(fields) + "\n")
    except OSError:
        pass
