"""scbi replay: rerun a step of a module from its replay file
(``$TVDIR/logs/<step>.cmd``, written when the step runs an interpreted
command hook), see scbi.steps.replay."""

from __future__ import annotations

import sys

from scbi.bashcompat import words
from scbi.steps import replay

USAGE = """
SCBI-REPLAY {version}

{argv0} replay [options] <step>.cmd

   -h | --help             this help message
   -v | --version          display driver & plug-ins versions
      | --trace            display each command before running it

Reruns a step from its replay file (in the logs directory of the module)."""


def main(driver, args: list[str]) -> int:
    argv = words(" ".join(args))
    if driver.get("DO_HELP") == "yes" or "-h" in argv or "--help" in argv:
        print(USAGE.format(version=driver.get("SCBI_VERSION"), argv0=driver.argv0))
        return 0
    trace = "--trace" in argv
    files = [a for a in argv if not a.startswith("-")]
    if len(files) != 1:
        sys.stderr.write("scbi replay: one replay file expected\n")
        return 1
    try:
        return replay.replay(files[0], trace=trace)
    except (OSError, ValueError, KeyError) as e:
        sys.stderr.write(f"scbi replay: {e}\n")
        return 1
