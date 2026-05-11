from __future__ import annotations

import datetime as dt
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .build_env import BuildEnv
from .models import ModuleRef, RefKind
from .plugin_loader_yaml import PluginLoader


def _parse_vcs_data(hook_list: list[str]) -> dict:
    proxy = hook_list[0] if len(hook_list) > 0 else "none"
    options = hook_list[1] if len(hook_list) > 1 else "none"
    vcs_name = hook_list[2] if len(hook_list) > 2 else "none"
    url = hook_list[3] if len(hook_list) > 3 else "none"
    directory = hook_list[4] if len(hook_list) > 4 else ""
    return {
        "proxy": proxy,
        "options": options,
        "name": vcs_name,
        "url": url,
        "dir": directory,
        "kind": vcs_name.lower(),
    }


def _parse_archive_data(hook_list: list[str]) -> dict:
    proxy = hook_list[0] if len(hook_list) > 0 else "none"
    options = hook_list[1] if len(hook_list) > 1 else "none"
    tool = hook_list[2] if len(hook_list) > 2 else "none"
    url = hook_list[3] if len(hook_list) > 3 else "none"
    filename = hook_list[4] if len(hook_list) > 4 else ""
    return {
        "proxy": proxy,
        "options": options,
        "tool": tool,
        "kind": tool,
        "url": url,
        "filename": filename,
    }


class SourceManager:
    def __init__(
        self,
        plugin_loader: PluginLoader,
        build_env: BuildEnv,
        do_update: bool = False,
        do_patch: bool = True,
        no_archive_cache: bool = False,
    ):
        self.loader = plugin_loader
        self.be = build_env
        self.do_update = do_update
        self.do_patch = do_patch
        self.no_archive_cache = no_archive_cache
        self.archives_dir = build_env.scbi_bdir / ".archives"
        self.vcs_dir = build_env.scbi_bdir / ".vcs"

    def _log_msg(self, msg: str) -> None:
        ts = dt.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        print(f"{ts} : {msg}", file=sys.stderr)

    def handle_sources(self, plugin, ref: ModuleRef) -> int:
        variant = ref.variant or "default"

        if variant == "native":
            self._write_source_id(f"native-{ref.version or 'NONE'}")
            self._write_source_ref(
                f"{plugin.name} none native revision {ref.version or 'NONE'}"
            )
            return 0

        if ref.kind == RefKind.VERSION:
            ver_tag = f" [{ref.version}]" if ref.version else ""
            self._log_msg(f"get sources from archive{ver_tag}")
            return self._handle_archive(plugin, ref)
        elif ref.kind in (RefKind.DEV, RefKind.BRANCH, RefKind.NONE):
            vcs_name = "git"
            ver_tag = f" [{ref.version}]" if ref.version and ref.version != "NONE" else ""
            self._log_msg(f"get sources from {vcs_name}{ver_tag}")
            return self._handle_vcs(plugin, ref)
        else:
            return self._handle_none(plugin, ref)

    def _write_source_id(self, content: str) -> None:
        root = self.be.module_root
        root.mkdir(parents=True, exist_ok=True)
        var_path = root / f"source-id-{self.be.variant}"
        var_path.write_text(content)
        latest = root / "source-id"
        latest.write_text(content)

    def _write_source_ref(self, content: str) -> None:
        path = self.be.module_root / "source-ref"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n")

    def _write_build_id(self, content: str) -> None:
        path = self.be.module_root / f"build-id-{self.be.variant}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def _get_build_id(self, for_module: str, module_ref: str, vid: str) -> str:
        raw = f"{self.be.scbi_prefix}:{self.be.scbi_target}:{for_module}:{module_ref}:{vid}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _handle_archive(self, plugin, ref: ModuleRef) -> int:
        results = self.loader.resolve_all_hooks(
            plugin, ref.variant, "archive"
        )
        if not results:
            print(
                f"scbi: error: {plugin.name}-archive hook not defined",
                file=sys.stderr,
            )
            return 1

        r = results[0]
        if not isinstance(r, list):
            return 1
        data = _parse_archive_data(r)
        data["filename"] = self.be.substitute(data["filename"])
        data["url"] = self.be.substitute(data["url"])

        if data["kind"].upper() in ("NONE",):
            self._write_source_id(f"none-{ref.version or 'NONE'}")
            self._write_source_ref(
                f"{plugin.name} none {self.be.variant} revision {ref.version or 'NONE'}"
            )
            return 0

        code = self._download_archive(data, plugin.name)
        if code != 0:
            return code

        code = self._extract_archive(data, plugin.name)
        if code != 0:
            return code

        archive_src = self.be.module_root / "archive-src"
        if archive_src.exists():
            src_link = self.be.module_root / "src"
            if src_link.exists() or src_link.is_symlink():
                src_link.unlink()
            os.symlink(
                os.path.relpath(archive_src, self.be.module_root),
                str(src_link),
            )

        ver = ref.version or "NONE"
        self._write_source_id(f"archive-{ver}")
        archive_sha1 = "NONE"
        sha1_file = self.be.module_root / "archive-sha1"
        if sha1_file.exists():
            archive_sha1 = sha1_file.read_text().strip().split()[0]
        self._write_source_ref(
            f"{plugin.name} archive {ver} sha-1 {archive_sha1}"
        )
        bid = self._get_build_id("", str(ref), f"archive-{ver}{archive_sha1}")
        self._write_build_id(bid)

        return 0

    def _handle_vcs(self, plugin, ref: ModuleRef) -> int:
        results = self.loader.resolve_all_hooks(
            plugin, ref.variant, "vcs"
        )
        if not results:
            return self._handle_none(plugin, ref)

        r = results[0]
        if not isinstance(r, list):
            return self._handle_none(plugin, ref)

        data = _parse_vcs_data(r)
        data["url"] = self.be.substitute(data["url"])
        vcs_kind = data["kind"]

        if vcs_kind in ("none",):
            return self._handle_none(plugin, ref)

        repo_name = Path(data["url"]).stem
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        repo_dir = self.vcs_dir / repo_name
        self.vcs_dir.mkdir(parents=True, exist_ok=True)

        module_root = self.be.module_root
        vcs_link = module_root / "vcs"
        src_link = module_root / "src"

        if ref.kind == RefKind.DEV:
            user_repo = self._get_user_co_dir(vcs_kind)
            if not user_repo or not (user_repo / repo_name).exists():
                print(
                    f"scbi: {plugin.name} cannot find local dev repository: "
                    f"{user_repo / repo_name}",
                    file=sys.stderr,
                )
                return 1

            if vcs_link.exists() or vcs_link.is_symlink():
                vcs_link.unlink()
            os.symlink(
                os.path.relpath(user_repo / repo_name, module_root),
                str(vcs_link),
            )
            import subprocess as sp
            commit_id = self._get_vcs_commit_id(False, vcs_kind, vcs_link)
            commit_short = self._get_vcs_commit_id(True, vcs_kind, vcs_link)
            rdev = f"-{commit_short}" if ref.version == "dev" else ""
            self._write_source_id(f"{ref.version or 'NONE'}{rdev}")
            bid = self._get_build_id("", str(ref), f"{ref.version}{commit_id}")
            self._write_build_id(bid)
        else:
            code = self._clone_or_update(vcs_kind, data, repo_name, repo_dir, plugin.name)
            if code != 0:
                return code

            if vcs_link.exists() or vcs_link.is_symlink():
                vcs_link.unlink()
            os.symlink(
                os.path.relpath(repo_dir, module_root),
                str(vcs_link),
            )

            self._switch_branch(vcs_kind, data, ref, vcs_link, plugin.name)

            ver = ref.version or "NONE"
            self._write_source_id(f"vcs-{ver}")
            bid_vid = self._get_vcs_build_id(vcs_kind, vcs_link)
            bid = self._get_build_id("", str(ref), bid_vid)
            self._write_build_id(bid)

        src_target = vcs_link if ref.kind == RefKind.DEV else repo_dir
        if not src_link.exists() and not src_link.is_symlink() and src_target.exists():
            os.symlink(
                os.path.relpath(src_target, module_root),
                str(src_link),
            )

        return 0

    def _handle_none(self, plugin, ref: ModuleRef) -> int:
        ver = ref.version or "NONE"
        self._write_source_id(f"none-{ver}")
        self._write_source_ref(
            f"{plugin.name} none {self.be.variant} revision {ver}"
        )
        bid = self._get_build_id("", str(ref), ver)
        self._write_build_id(bid)
        return 0

    def _download_archive(self, data: dict, module: str) -> int:
        tool = data["tool"].lower()
        if tool in ("none",):
            return 0

        url = data["url"].rstrip("/")
        filename = data["filename"]
        if not filename:
            return 0

        self.archives_dir.mkdir(parents=True, exist_ok=True)
        dest = self.archives_dir / filename

        if dest.exists() and not self.no_archive_cache:
            return 0

        full_url = f"{url}/{filename}"

        if tool in ("curl", "wget"):
            cmd = []
            if tool == "curl":
                cmd = ["curl", "-fsSL", full_url, "--output", str(dest)]
            else:
                cmd = ["wget", "-q", full_url, "-O", str(dest)]

            print(
                f"scbi: {module} get sources from archive",
                file=sys.stderr,
            )
            result = subprocess.run(
                cmd, capture_output=True, text=True
            )
            if result.returncode != 0:
                dest.unlink(missing_ok=True)
                print(
                    f"scbi: error: cannot get archive from {full_url}",
                    file=sys.stderr,
                )
                return 1

            sha1_url = f"{url}/{filename}.sha1"
            sha1_dest = self.archives_dir / f"{filename}.sha1"
            if tool == "curl":
                subprocess.run(
                    ["curl", "-fsSL", sha1_url, "--output", str(sha1_dest)],
                    capture_output=True,
                )
            else:
                subprocess.run(
                    ["wget", "-q", sha1_url, "-O", str(sha1_dest)],
                    capture_output=True,
                )
        elif tool in ("cp",):
            src_path = Path(url) / filename
            if src_path.exists():
                shutil.copy2(str(src_path), str(dest))
            else:
                print(
                    f"scbi: error: cannot copy archive from {src_path}",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                f"scbi: error: unknown archive tool {tool}",
                file=sys.stderr,
            )
            return 1

        return 0

    def _extract_archive(self, data: dict, module: str) -> int:
        filename = data["filename"]
        archive_path = self.archives_dir / filename

        if not archive_path.exists():
            print(
                f"scbi: error: archive {filename} not found",
                file=sys.stderr,
            )
            return 1

        module_root = self.be.module_root
        archive_src = module_root / "archive-src"
        archive_link = module_root / "archive"
        sha1_link = module_root / "archive-sha1"

        if archive_src.exists():
            shutil.rmtree(str(archive_src))
        archive_link.unlink(missing_ok=True)
        sha1_link.unlink(missing_ok=True)

        print(
            f"scbi: {module} extract archive {filename}",
            file=sys.stderr,
        )

        tmpdir = module_root / "archivetmp"
        tmpdir.mkdir(parents=True, exist_ok=True)

        try:
            if filename.endswith(".zip"):
                with zipfile.ZipFile(str(archive_path), "r") as zf:
                    zf.extractall(str(tmpdir))
            elif filename.endswith(".tar.zst"):
                print(
                    f"scbi: error: zst extraction not supported natively",
                    file=sys.stderr,
                )
                return 1
            elif (
                filename.endswith(".tar.gz")
                or filename.endswith(".tgz")
                or filename.endswith(".tar.xz")
                or filename.endswith(".tar.bz2")
                or filename.endswith(".tar")
            ):
                with tarfile.open(str(archive_path), "r:*") as tf:
                    tf.extractall(str(tmpdir))
            else:
                print(
                    f"scbi: error: unknown archive format {filename}",
                    file=sys.stderr,
                )
                return 1
        except Exception as e:
            print(
                f"scbi: error: archive {filename} is corrupted: {e}",
                file=sys.stderr,
            )
            return 1

        entries = list(tmpdir.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            topdir = entries[0]
            shutil.move(str(topdir), str(archive_src))
        else:
            archive_src.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                shutil.move(str(entry), str(archive_src))

        shutil.rmtree(str(tmpdir))

        os.symlink(
            os.path.relpath(archive_path, module_root),
            str(archive_link),
        )
        sha1_path = self.archives_dir / f"{filename}.sha1"
        if sha1_path.exists():
            os.symlink(
                os.path.relpath(sha1_path, module_root),
                str(sha1_link),
            )

        return 0

    def _clone_or_update(
        self, vcs_kind: str, data: dict, repo_name: str,
        repo_dir: Path, module: str
    ) -> int:
        url = data["url"]

        if vcs_kind == "git":
            if not repo_dir.exists():
                print(
                    f"scbi: {module} get sources from git",
                    file=sys.stderr,
                )
                result = subprocess.run(
                    ["git", "clone", "--recursive", url, str(repo_dir)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    print(
                        f"scbi: error: cannot clone {url}",
                        file=sys.stderr,
                    )
                    return 1
            else:
                git_dir = repo_dir / ".git"
                if not git_dir.exists():
                    print(
                        f"scbi: error: {repo_dir} not a git repository",
                        file=sys.stderr,
                    )
                    return 1
                subprocess.run(
                    ["git", "remote", "set-url", "origin", url],
                    cwd=str(repo_dir),
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "fetch", "--force", "--tags"],
                    cwd=str(repo_dir),
                    capture_output=True,
                )

        elif vcs_kind in ("mercurial", "hg"):
            if not repo_dir.exists():
                print(
                    f"scbi: {module} get sources from mercurial",
                    file=sys.stderr,
                )
                result = subprocess.run(
                    ["hg", "clone", url, str(repo_dir)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    print(
                        f"scbi: error: cannot clone {url}",
                        file=sys.stderr,
                    )
                    return 1
            else:
                subprocess.run(
                    ["hg", "pull"],
                    cwd=str(repo_dir),
                    capture_output=True,
                )

        elif vcs_kind in ("subversion", "svn"):
            if not repo_dir.exists():
                print(
                    f"scbi: {module} get sources from subversion",
                    file=sys.stderr,
                )
                result = subprocess.run(
                    ["svn", "co", url, str(repo_dir)],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    return 1
            else:
                subprocess.run(
                    ["svn", "update"],
                    cwd=str(repo_dir),
                    capture_output=True,
                )

        return 0

    def _switch_branch(
        self, vcs_kind: str, data: dict, ref: ModuleRef,
        vcs_link: Path, module: str
    ) -> int:
        branch = ref.version
        if branch in ("NONE", "", None):
            branch = None

        if branch is None:
            return 0

        if vcs_kind == "git":
            result = subprocess.run(
                [
                    "git", "show-ref", "--verify", "--quiet",
                    f"refs/remotes/origin/{branch}",
                ],
                cwd=str(vcs_link),
                capture_output=True,
            )
            if result.returncode == 0:
                ref_spec = f"refs/remotes/origin/{branch}"
            else:
                result = subprocess.run(
                    [
                        "git", "show-ref", "--verify", "--quiet",
                        f"refs/tags/{branch}",
                    ],
                    cwd=str(vcs_link),
                    capture_output=True,
                )
                if result.returncode == 0:
                    ref_spec = f"refs/tags/{branch}"
                else:
                    result = subprocess.run(
                        [
                            "git", "rev-parse", "-q", "--verify",
                            f"{branch}^{{commit}}",
                        ],
                        cwd=str(vcs_link),
                        capture_output=True,
                    )
                    if result.returncode != 0:
                        print(
                            f"scbi: error: cannot switch git branch {branch}",
                            file=sys.stderr,
                        )
                        return 1
                    ref_spec = branch

            subprocess.run(
                ["git", "checkout", "--force", "master"],
                cwd=str(vcs_link),
                capture_output=True,
            )
            subprocess.run(
                ["git", "fetch", "--tags"],
                cwd=str(vcs_link),
                capture_output=True,
            )

            build_branch = "scbi"
            result = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet",
                 f"refs/heads/{build_branch}"],
                cwd=str(vcs_link),
                capture_output=True,
            )
            if result.returncode != 0:
                subprocess.run(
                    ["git", "branch", build_branch],
                    cwd=str(vcs_link),
                    capture_output=True,
                )

            subprocess.run(
                ["git", "checkout", build_branch],
                cwd=str(vcs_link),
                capture_output=True,
            )
            subprocess.run(
                ["git", "reset", "--hard", ref_spec],
                cwd=str(vcs_link),
                capture_output=True,
            )

        elif vcs_kind in ("mercurial", "hg"):
            default_branch = "default" if branch is None else branch
            subprocess.run(
                ["hg", "branch", "-f", default_branch],
                cwd=str(vcs_link),
                capture_output=True,
            )

        elif vcs_kind in ("subversion", "svn"):
            subprocess.run(
                ["svn", "switch", f"^/branches/{branch}"],
                cwd=str(vcs_link),
                capture_output=True,
            )

        return 0

    def _get_user_co_dir(self, vcs_kind: str) -> Path | None:
        if vcs_kind == "git":
            repo_env = os.environ.get("SCBI_GIT_REPO", "")
        elif vcs_kind in ("mercurial", "hg"):
            repo_env = os.environ.get("SCBI_HG_REPO", "")
        elif vcs_kind in ("subversion", "svn"):
            repo_env = os.environ.get("SCBI_SVN_REPO", "")
        else:
            return None
        return Path(repo_env) if repo_env else None

    def _get_vcs_commit_id(self, short: bool, vcs_kind: str, vcs_dir: Path) -> str:
        try:
            if vcs_kind == "git":
                flag = "--short=6" if short else ""
                result = subprocess.run(
                    ["git", "rev-parse"] + ([flag] if flag else []) + ["HEAD"],
                    cwd=str(vcs_dir),
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            elif vcs_kind in ("mercurial", "hg"):
                result = subprocess.run(
                    ["hg", "id", "-i"],
                    cwd=str(vcs_dir),
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            elif vcs_kind in ("subversion", "svn"):
                result = subprocess.run(
                    ["svn", "log", "-l", "1"],
                    cwd=str(vcs_dir),
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if line.startswith("r"):
                            return line.split()[0]
        except Exception:
            pass
        return ""

    def _get_vcs_build_id(self, vcs_kind: str, vcs_link: Path) -> str:
        try:
            if vcs_kind == "git":
                gver = subprocess.run(
                    ["git", "rev-list", "-1", "HEAD", "--"],
                    cwd=str(vcs_link),
                    capture_output=True, text=True,
                ).stdout.strip()
                gdif = subprocess.run(
                    ["git", "diff", "HEAD", "--"],
                    cwd=str(vcs_link),
                    capture_output=True, text=True,
                ).stdout
                gdif_hash = hashlib.md5(gdif.encode()).hexdigest()
                return gver + gdif_hash
            elif vcs_kind in ("mercurial", "hg"):
                hver = subprocess.run(
                    ["hg", "identify", "--num"],
                    cwd=str(vcs_link),
                    capture_output=True, text=True,
                ).stdout.strip()
                hdif = subprocess.run(
                    ["hg", "diff"],
                    cwd=str(vcs_link),
                    capture_output=True, text=True,
                ).stdout
                lines = hdif.splitlines()
                if len(lines) > 3:
                    hdif = "\n".join(lines[3:])
                hdif_hash = hashlib.md5(hdif.encode()).hexdigest()
                return hver + hdif_hash
            elif vcs_kind in ("subversion", "svn"):
                result = subprocess.run(
                    ["svn", "info"],
                    cwd=str(vcs_link),
                    capture_output=True, text=True,
                )
                for line in result.stdout.splitlines():
                    if line.startswith("Revision:"):
                        return "r" + line.split()[1]
        except Exception:
            pass
        return "0"
