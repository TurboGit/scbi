"""Command line entry point of the Python SCBI driver."""

from __future__ import annotations

import os
import sys

from scbi.driver import Driver
from scbi.errors import Exit, NotImplementedYet
from scbi.plugin.formats import PluginFormatError
from scbi.plugin.registry import LegacyPluginError


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    #  $0 of the Bash driver (the wrapper script gives its own)
    argv0 = os.environ.get("SCBI_ARGV0", "scbi")
    driver = Driver(argv0)
    try:
        return driver.main(argv)
    except Exit as e:
        return e.status
    except (LegacyPluginError, PluginFormatError) as e:
        sys.stdout.flush()
        print(f"error: {e}", file=sys.stderr)
        return 1
    except NotImplementedYet as e:
        sys.stdout.flush()
        print(f"scbi (python): not implemented yet: {e}", file=sys.stderr)
        return 1
    finally:
        sys.stdout.flush()
        driver.clean_up()
