from scbi.bashcompat import words
from scbi.sources.archive.base import Downloader


class Ftp(Downloader):
    names = ("ftp",)

    def output_args(self, dest: str) -> list[str]:
        return ["-o", *words(dest)]
