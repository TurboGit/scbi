from scbi.bashcompat import words
from scbi.sources.archive.base import Downloader


class Copy(Downloader):
    """cp (local or mounted file systems) and scp: the destination is the
    last argument."""

    names = ("cp", "scp")

    def output_args(self, dest: str) -> list[str]:
        return words(dest)
