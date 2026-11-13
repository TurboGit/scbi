from scbi.bashcompat import words
from scbi.sources.archive.base import Downloader


class Wget(Downloader):
    names = ("wget",)

    def output_args(self, dest: str) -> list[str]:
        return ["-O", *words(dest)]
