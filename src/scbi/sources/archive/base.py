"""Download protocol interface (the protocol field of the archive hook).

``$tarcp $options $tarurl/$tarsrc <output>`` in get-archive: a protocol
only says how the output file is given to its tool. Adding one is a
module with a ``Downloader`` and one entry in registry.py.
"""

from __future__ import annotations

from scbi.bashcompat import words


class Downloader:
    names: tuple[str, ...] = ()

    def output_args(self, dest: str) -> list[str]:
        raise NotImplementedError

    def command(self, name: str, options: str, url: str, dest: str) -> list[str]:
        """The command line (all the parts are unquoted in Bash)."""
        return [*words(name), *words(options), *words(url), *self.output_args(dest)]
