"""Git: the commands of branch (scbi.sources.vcs.git)."""

from scbi.sources.vcs.git import Git


class FakeRun:
    """A VcsRun recording the commands (all succeed)."""

    def __init__(self):
        self.bdir = "/b"
        self.cwd = "/b"
        self.calls: list[tuple[str, ...]] = []

    def cd(self, path):
        self.cwd = path
        return True

    def run(self, *args):
        self.calls.append(args)
        return 0

    def output(self, *args):
        self.calls.append(args)
        return 0, "abc123"

    def isfile(self, path):
        return False

    def mail(self, msg):
        pass


def fetches(fetch: bool) -> list[tuple[str, ...]]:
    r = FakeRun()
    assert Git().branch(r, "", "m", "main", "", fetch=fetch) == 0
    return [c for c in r.calls if c[:2] == ("git", "fetch")]


def test_branch_fetches_the_tags_of_origin_only_when_asked():
    #  not after the checkout of an existing clone (git fetch --force
    #  --tags), nor without --update
    assert fetches(True) == [("git", "fetch", "origin", "--tags")]
    assert fetches(False) == []
