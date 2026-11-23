from scbi.bashcompat import words
from scbi.sources.archive.base import Downloader


class Curl(Downloader):
    names = ("curl",)

    def command(self, name: str, options: str, url: str, dest: str) -> list[str]:
        """--fail: an HTTP error (404...) is an error, not a page saved
        as the archive."""
        return [*words(name), "--fail", *words(options), *words(url), *self.output_args(dest)]

    def output_args(self, dest: str) -> list[str]:
        return ["--output", *words(dest)]
