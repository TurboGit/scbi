"""The isolated environment of interpreted command hooks (steps/hookenv.py)."""

from scbi.steps.hookenv import hook_environment


def test_hook_environment():
    initial = {"PATH": "/usr/bin", "HOME": "/h", "LC_ALL": "C", "http_proxy": "p", "HTTPS_PROXY": "q",
               "CC": "gcc", "EDITOR": "vi", "SSH_AUTH_SOCK": "/s", "CFLAGS": "-O2"}
    exported = {**initial, "CFLAGS": "-O2 -g",           # changed by an env action
                "SCBI_TARGET": "x86_64", "PKG_CONFIG_PATH": "/p/lib/pkgconfig",
                "BASH_FUNC_f%%": "() { true; }"}
    env = hook_environment(exported, initial)
    assert env == {"PATH": "/usr/bin", "HOME": "/h", "LC_ALL": "C", "http_proxy": "p", "HTTPS_PROXY": "q",
                   "CFLAGS": "-O2 -g", "SCBI_TARGET": "x86_64", "PKG_CONFIG_PATH": "/p/lib/pkgconfig"}


def test_path_changed_is_kept():
    env = hook_environment({"PATH": "/x:/usr/bin"}, {"PATH": "/usr/bin"})
    assert env == {"PATH": "/x:/usr/bin"}
