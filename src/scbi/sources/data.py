"""The data of the vcs and archive hooks (ports of get-vcs-data and
get-archive-data, check-archive-exists, get-vcs-dir).

These functions are always used as ``( $(get-...-data ...) )`` in Bash:
an ``exit`` only ends the command substitution and the error message goes
to stderr. So they return ``(words, status)`` and never raise.
"""

from __future__ import annotations

import os

from scbi.bashcompat import words
from scbi.hooks.exec import quote
from scbi.plugin.resolve import get_hook

#  VCS name -> the variable holding the users' checkout directory
#  (get-vcs-user-co-dir / get-vcs-dir)
USER_CO_DIRS = {"git": "SCBI_GIT_REPO", "svn": "SCBI_SVN_REPO", "subversion": "SCBI_SVN_REPO",
                "hg": "SCBI_HG_REPO"}


def _hook_variant(function: str, module: str, hook: str) -> str:
    v = function[len(module):] if function.startswith(module) else function
    v = v[:-len(f"-{hook}")] if v.endswith(f"-{hook}") else v
    v = v[1:] if v.startswith("-") else v
    return v or "default"


def _call(builder, function: str, module: str, variant: str, args: list[str], rewrite: str) -> list[str]:
    d = builder.d
    out = d.runner().call_value(function, module, variant, args, d.plan, builder.modules_list)
    if builder.fn_exists(rewrite):
        #  scbi-rewrite-xxx $($FUNCTION ...): a user function
        vals = " ".join(quote(w) for w in words("\n".join(out)))
        return words(builder.capture(module, variant, f"{rewrite} {vals}"))
    return words("\n".join(out))


def vcs_data(builder, module: str, variant: str) -> tuple[list[str], int]:
    """``get-vcs-data MODULE VARIANT``: [variant, proxy, options, name,
    url, (dir)] as words."""
    if not builder.ported("get-vcs-data"):
        return builder.bash_words(module, variant, f"get-vcs-data {quote(module)} {quote(variant)}")
    d = builder.d
    function = get_hook(d.registry, module, variant, "vcs", d.runner().cross) or f"{module}-vcs"
    vcs_variant = _hook_variant(function, module, "vcs")
    specific = d.get(f"SCBI_{module.replace('-', '_')}_VCS_VARIANT")
    if specific:
        if builder.fn_exists(f"{module}-{specific}-vcs"):
            vcs_variant, function = specific, f"{module}-{specific}-vcs"
        else:
            d.log.elog(module, "vcs", "specific", "function", "for", "not", "found")
            return [], 1
    elif d.get("SCBI_VCS_VARIANT"):
        gv = d.get("SCBI_VCS_VARIANT")
        if builder.fn_exists(f"{module}-{gv}-vcs"):
            vcs_variant, function = gv, f"{module}-{gv}-vcs"
    if not builder.fn_exists(function):
        return [], 1
    return [*words(vcs_variant), *_call(builder, function, module, variant, [], "scbi-rewrite-vcs")], 0


def archive_data(builder, module: str, variant: str, version: str) -> tuple[list[str], int]:
    """``get-archive-data MODULE VARIANT VERSION``: [variant, proxy,
    options, protocol, url, file, (dir)] as words.

    The Bash function uses the caller's ``$module`` in places; all the
    callers have it equal to MODULE."""
    if not builder.ported("get-archive-data"):
        return builder.bash_words(module, variant, (
            f"module={quote(module)}; get-archive-data {quote(module)} {quote(variant)} {quote(version)}"))
    d = builder.d
    function = get_hook(d.registry, module, variant, "archive", d.runner().cross) or f"{module}-archive"
    archive_variant = _hook_variant(function, module, "archive")
    if variant != "native":
        specific = d.get(f"SCBI_{module.replace('-', '_')}_ARCHIVE_VARIANT")
        if specific:
            if builder.fn_exists(f"{module}-{specific}-archive"):
                archive_variant, function = specific, f"{module}-{specific}-archive"
            else:
                d.log.elog(module, "tar", "specific", "function", "not", "found")
                return [], 1
        elif d.get("SCBI_ARCHIVE_VARIANT"):
            gv = d.get("SCBI_ARCHIVE_VARIANT")
            if builder.fn_exists(f"{module}-{gv}-archive"):
                archive_variant, function = gv, f"{module}-{gv}-archive"
    if not builder.fn_exists(function):
        return [], 1
    return [*words(archive_variant),
            *_call(builder, function, module, variant, [*words(version)], "scbi-rewrite-archive")], 0


def archive_exists(builder, module: str, variant: str, version: str) -> bool:
    """``check-archive-exists``: the archive file is in SCBI_ARCHIVES."""
    if not builder.ported("check-archive-exists"):
        return builder.run(module, variant, (
            f"module={quote(module)}; check-archive-exists {quote(module)} {quote(variant)} {quote(version)}")) == 0
    tar, status = archive_data(builder, module, variant, version)
    if status != 0:
        return False
    tarsrc = tar[5] if len(tar) > 5 else ""
    return os.path.isfile(f"{builder.get('SCBI_ARCHIVES')}/{tarsrc}")


def vcs_dir(builder, modref: str) -> tuple[str, int]:
    """``get-vcs-dir MODREF`` (output, status: 1 after an error)."""
    d = builder.d
    if not builder.ported("get-vcs-dir"):
        info = (d.plan.module_ref(modref) + ["", ""])[:2]
        out, rc = builder.bash_words(info[0], info[1], f"get-vcs-dir {quote(modref)}")
        return " ".join(out), rc
    info = (d.plan.module_ref(modref) + [""] * 4)[:4]
    module, variant, kind = info[:3]
    vcs, _ = vcs_data(builder, module, variant)
    name = vcs[3] if len(vcs) > 3 else ""
    url = vcs[4] if len(vcs) > 4 else ""
    repo = os.path.basename(url.rstrip("/")) if url else ""
    if repo.endswith(".git") and repo != ".git":
        repo = repo[:-4]
    if kind == "DEV":
        var = {"git": "SCBI_GIT_REPO", "svn": "SCBI_SVN_REPO", "subversion": "SCBI_SVN_REPO",
               "hg": "SCBI_HG_REPO", "mercurial": "SCBI_HG_REPO"}.get(name)
        if var is None:
            d.log.elog(module, "unsupported", "VCS", *words(name))
            return "", 1
        return " ".join(words(f"{d.get(var)}/{repo}")), 0
    return " ".join(words(f"{d.get('SCBI_BDIR')}/.vcs/{module}")), 0


def display_ref(name: str, ref: str) -> str:
    """``get-vcs-display-ref``."""
    if ref == "dev":
        return ref
    default = {"git": "master", "hg": "default", "mercurial": "default",
               "svn": "trunk", "subversion": "trunk"}.get(name)
    return ref.replace("NONE", default, 1) if default else ref


def user_co_dir(builder, name: str) -> str:
    """``get-vcs-user-co-dir`` (NONE for an unknown VCS; mercurial is not
    accepted here, only hg)."""
    var = USER_CO_DIRS.get(name)
    return builder.get(var) if var else "NONE"
