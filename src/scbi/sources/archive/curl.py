from scbi.bashcompat import words
from scbi.sources.archive.base import Downloader


class Curl(Downloader):
    names = ("curl",)

    def output_args(self, dest: str) -> list[str]:
        return ["--output", *words(dest)]
