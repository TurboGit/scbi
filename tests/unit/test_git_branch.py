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


def test_checkout_without_fetch(tmp_path):
    #  an existing clone already updated (prefetch): no fetch
    (tmp_path / ".vcs" / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "m").mkdir()

    class DirRun(FakeRun):
        def __init__(self):
            super().__init__()
            self.bdir = self.cwd = str(tmp_path)

        def cd(self, path):
            import os
            self.cwd = os.path.normpath(os.path.join(self.cwd, path))
            return os.path.isdir(self.cwd)

        def isdir(self, path):
            import os
            return os.path.isdir(os.path.join(self.cwd, path))

        def isfile(self, path):
            return False

    for fetch, expected in ((True, [("git", "fetch", "origin", "--force", "--tags", "--recurse-submodules")]),
                            (False, [])):
        r = DirRun()
        assert Git().checkout(r, "/r/repo.git", "", "m", "", fetch=fetch) == 0
        assert [c for c in r.calls if c[:2] == ("git", "fetch")] == expected
