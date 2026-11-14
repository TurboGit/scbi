"""OS packages: port of the package queries of scripts.d/6_distpkg
(``check-<os>-pkg``, ``check-pkg``, ``check-pkg-status``,
``clean-version-string``) and of the auto variants of scripts.d/9_versions
(``check-auto-variant``, ``handle-plan-auto-variant``).

The installed packages (SCBI_PKGS) and the aliases (SCBI_ALIAS) are the
arrays of the driver variables. A distribution is supported when it has
an entry in CHECKERS.
"""

from __future__ import annotations

import os
import re
import subprocess

from scbi.bashcompat import words
from scbi.vercmp import check_versions, get_version_number
from scbi.walker import array, get_pkg_name

VERSION_OK = 0
VERSION_NOK = 1
PKG_NOT_INSTALLED = 2
PKG_NOT_FOUND = 3
ERROR_HOOK_NOT_FOUND = 4
ERROR_PLUGIN_NOT_FOUND = 5


def clean_version_string(version: str) -> str:
    """Port of ``clean-version-string``."""
    r = version.split(":", 1)[1] if ":" in version else version
    for pat in ("-", "+repack", "+dfsg", "~"):
        i = r.rfind(pat)
        if i >= 0:
            r = r[:i]
    return r


def _output(argv: list[str]) -> str:
    """Standard output of a command (LANG=C), errors ignored."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, errors="replace",
                              env={**os.environ, "LANG": "C"}).stdout
    except OSError:
        return ""


def _installed(pkgs: dict[str, str], pck: str, version: str) -> int:
    """The installed version against the required one."""
    req = get_version_number((words(version) or [""])[0])
    return VERSION_OK if check_versions(pkgs[pck], ">=", req) else VERSION_NOK


def check_deb(pkgs: dict[str, str], pck: str, version: str) -> int:
    """Port of ``check-deb-pkg`` (and ``check-ubt-pkg``)."""
    if pkgs.get(pck):
        return _installed(pkgs, pck, version)
    cand = []
    for line in _output(["apt-cache", "policy", pck]).splitlines():
        if "Candidate" in line:
            cand += words(line)
    if len(cand) > 1 and cand[1]:
        pkgs[pck] = clean_version_string(cand[1])
        return PKG_NOT_INSTALLED
    return PKG_NOT_FOUND


def check_mingw(pkgs: dict[str, str], pck: str, version: str) -> int:
    """Port of ``check-mingw-pkg``."""
    if pkgs.get(pck):
        return _installed(pkgs, pck, version)
    cand = words(_output(["pacman", "--sync", "--search", pck]))
    if len(cand) > 1 and cand[1]:
        pkgs[pck] = clean_version_string(cand[1])
        return PKG_NOT_INSTALLED
    return PKG_NOT_FOUND


def check_cos(pkgs: dict[str, str], pck: str, version: str) -> int:
    """Port of ``check-cos-pkg`` (and fed, rhl)."""
    if pkgs.get(pck):
        return _installed(pkgs, pck, version)
    try:
        rc = subprocess.run(["dnf", "-C", "list", pck], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode
    except OSError:
        rc = 127
    return PKG_NOT_INSTALLED if rc == 0 else PKG_NOT_FOUND


def check_none(pkgs: dict[str, str], pck: str, version: str) -> int:
    return VERSION_OK


#  check-<os>-pkg per distribution (SCBI_OS_NAME)
CHECKERS = {
    "deb": check_deb, "ubt": check_deb, "cos": check_cos, "fed": check_cos, "rhl": check_cos,
    "mingw": check_mingw, "none": check_none, "win": check_none,
}

class OsPackages:
    def __init__(self, driver):
        self.d = driver
        self.os_name = driver.get("SCBI_OS_NAME")
        #  a copy: in Bash the queries run in sub-shells (the parallel
        #  auto-variant jobs), a candidate version they record is not kept
        self.pkgs = dict(array(driver, "SCBI_PKGS"))

    def check_os(self, pck: str, version: str) -> int:
        """``check-${SCBI_OS_NAME}-pkg PCK VERSION`` (the fake OS of the
        testsuite, scbi.setup.TEST_OS, is checked as Debian)."""
        checker = CHECKERS.get(self.os_name)
        if checker is None:
            testsuite = self.d.get("SCBI_TESTSUITE") == "yes"
            checker = check_deb if self.os_name == "test" and testsuite else check_none
        return checker(self.pkgs, pck, version)

    @staticmethod
    def _name_ver(arg: str) -> tuple[str, str]:
        #  ( ${1/:/ } )
        nv = words(arg.replace(":", " ", 1))
        return (nv + ["", ""])[0], (nv + ["", ""])[1]

    def check_pkg(self, arg: str, out) -> int:
        """Port of ``check-pkg PKG[:VERSION]``: messages to ``out``;
        0 installed, 1 not installed or wrong version, 2 not found."""
        pkg, version = self._name_ver(arg)
        msg = "warning" if self.d.get("DO_WARNING_EXTERNAL") == "yes" else "error"
        cpres = 0
        for distname in words(get_pkg_name(self.d, pkg)):
            res = self.check_os(distname, version)
            if res == PKG_NOT_FOUND:
                out(f"{msg}: {distname} not found")
                cpres = 2
            elif res == PKG_NOT_INSTALLED:
                if version == "NONE":
                    out(f"{msg}: {distname} should be installed")
                else:
                    out(f"{msg}: {distname}:{version} should be installed")
                cpres = 1
            elif res == VERSION_NOK:
                out(f"{msg}: {distname}:{version} should be installed")
                cpres = 1
        return cpres

    def check_pkg_status(self, arg: str) -> list[str]:
        """Port of ``check-pkg-status``: 4 fields per package (status,
        required version, OS version, package name)."""
        pkg, version = self._name_ver(arg)
        result: list[str] = []
        for distname in words(get_pkg_name(self.d, pkg)):
            res = self.check_os(distname, version or "0")
            result += [str(res), *words(version or "0"), *words(self.pkgs.get(distname) or "0"),
                       *words(distname)]
        return result

    # ------------------------------------------------------------ auto

    def check_auto_variant(self, builder, module: str, formodule: str) -> list[str]:
        """Port of ``check-auto-variant``: 5 fields per OS dependency of the
        native variant (v|n, then the check-pkg-status fields)."""
        reg = self.d.registry
        if reg.plugin_file(module) is None:
            return ["n", str(ERROR_PLUGIN_NOT_FOUND), "0", "0", "NONE"]
        reg.load_module(module)
        if not builder.fn_exists(f"{module}-native-depends"):
            return ["n", str(ERROR_HOOK_NOT_FOUND), "0", "0", "NONE"]
        result: list[str] = []
        for dmodule in builder.get_all_depends(module, "native", "depends"):
            if reg.plugin_file(dmodule) is not None:
                continue
            if dmodule.split(":", 1)[1:] == ["[v]"]:
                mmod = "v"
                dmodule = dmodule[:dmodule.rfind(":")]
                info = self.d.plan.module_ref(*([module, formodule] if formodule else [module]))
                ref = (info + [""] * 4)[3]
                if ref != "NONE":
                    dmodule = f"{dmodule}:{ref}"
            else:
                mmod = "n"
            stats = self.check_pkg_status(dmodule)
            if stats and stats[0]:
                result += [mmod, *stats]
        return result

    def plan_auto_variant(self, builder, m: str) -> list[str]:
        """Port of ``handle-plan-auto-variant M``: its output lines
        (``0 M VALUE`` new plan entry, ``1 M MSG`` message, ``2 M MSG``
        error)."""
        value = self.d.plan.modver.get(m, "")
        mod = re.sub(r".*=", "", m, count=1, flags=re.S)
        formodule = m[:len(m) - len(mod)] if mod and m.endswith(mod) else m
        formodule = formodule[:-1] if formodule.endswith("=") else formodule

        info = self.d.plan.module_ref(*([value, formodule] if formodule else [value]))
        _module, variant, _kind, ref = (info + [""] * 4)[:4]
        if ref == "skip" or not re.match(r"auto(\.|$)", variant):
            return []

        pkver = self.check_auto_variant(builder, mod, formodule or "@root")
        entries = [pkver[k:k + 5] + [""] * (5 - len(pkver[k:k + 5])) for k in range(0, len(pkver), 5)]
        gstatus, gosverv, gosvern = str(VERSION_OK), "0", "0"
        for v, status, _mver, osver, _pkg in entries:
            gstatus = status
            if status != str(VERSION_OK):
                break
            if v == "v":
                gosverv = osver
            else:
                gosvern = osver
        gosver = gosverv if gosverv != "0" else gosvern

        ref = "" if ref == "NONE" else f" {ref}"
        lines: list[str] = []

        def echo(*args: str) -> None:
            lines.append(" ".join(args))

        if gstatus == str(VERSION_OK):
            value = re.sub(r"/auto[.a-zA-Z]*", "/native", value, count=1)
            head = value[:value.rfind(":")] if ":" in value else value
            echo("0", *words(m), f"{head}:{gosver}")
            echo("1", *words(m), f"%B%t{m}%c%g{ref}%c using %B%tnative%c variant")
        elif gstatus != str(ERROR_HOOK_NOT_FOUND):
            value = value.replace("/auto.", "/", 1)
            if not formodule:
                value = value.replace("/auto", "", 1)
            else:
                value = value.replace("/auto", "/" + re.sub(r"[-._]", "", formodule), 1)
            echo("0", *words(m), value)
            echo("1", *words(m), f"%B%t{m}%c%g{ref}%c using %B%tstandard%c variant")

        for _v, status, mver, osver, pkg in entries:
            if status == str(PKG_NOT_INSTALLED):
                if osver == "0":
                    echo("1", *words(m), f"\u00a0\u00a0↳ {pkg} not installed")
                else:
                    echo("1", *words(m), f"\u00a0\u00a0↳ {pkg} {osver} not installed")
            elif status == str(PKG_NOT_FOUND):
                echo("1", *words(m), f"\u00a0\u00a0↳ unknown dependency {pkg}")
            elif status == str(VERSION_NOK):
                if not ref:
                    echo("1", *words(m), f"\u00a0\u00a0↳ {pkg} {mver} installed {osver}")
                else:
                    echo("1", *words(m), f"\u00a0\u00a0↳ {pkg} {osver} installed")
            elif status == str(VERSION_OK):
                echo("1", *words(m), f"\u00a0\u00a0↳ {pkg} {osver} used")
            elif status == str(ERROR_HOOK_NOT_FOUND):
                echo("2", *words(m), f"{m} auto mode must define a native variant")
        return lines
