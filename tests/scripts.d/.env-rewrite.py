"""Environment of test050: the vcs records are rewritten (Python version
of .env-rewrite)."""

import os


def rewrite_vcs(record):
    proxy, options, vcs, url, *rest = record + [""] * (5 - len(record))
    url = url.replace("/this.is.path", os.environ.get("TESTREPOS", ""), 1)
    url = url.replace("some/dir", "lib1.bundle", 1)
    return [proxy, options, vcs, url, *rest]
