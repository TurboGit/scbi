"""Running the commands of the sources step (VCS and archive tools):
the environment, the current directory and the module log."""

from __future__ import annotations

import dataclasses
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TextIO

from scbi.log import Logger


@dataclass
class Run:
    """What the VCS commands run with: the environment (with the proxy
    settings), the build directory and the module log where the output of
    the commands goes (``>> $log 2>&1`` in Bash); messages logged by the
    implementations go there too."""

    env: dict[str, str]
    bdir: str
    log: TextIO
    logger: Logger
    mail: Callable[[str], None] = lambda msg: None
    cwd: str = field(default_factory=os.getcwd)

    @classmethod
    def to_log(cls, env: dict[str, str], bdir: str, log: TextIO, logger: Logger,
               mail: Callable[[str], None] = lambda msg: None) -> Run:
        return cls(env, bdir, log, dataclasses.replace(logger, stdout=log, stderr=log), mail)

    def cd(self, path: str) -> bool:
        """``cd PATH`` (relative to the current directory of the run)."""
        target = os.path.normpath(os.path.join(self.cwd, path))
        if os.path.isdir(target):
            self.cwd = target
            return True
        self.log.write(f"bash: cd: {path}: No such file or directory\n")
        self.log.flush()
        return False

    def run(self, *args: str) -> int:
        """A command, its output (stdout and stderr) to the log."""
        self.log.flush()
        try:
            return subprocess.run(list(args), cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
                                  stdout=self.log, stderr=subprocess.STDOUT).returncode
        except FileNotFoundError:
            self.log.write(f"bash: {args[0]}: command not found\n")
            self.log.flush()
            return 127

    def output(self, *args: str) -> tuple[int, str]:
        """``$(command)``: its output (trailing newlines removed), stderr to
        the log."""
        self.log.flush()
        try:
            proc = subprocess.run(list(args), cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=self.log)
        except FileNotFoundError:
            self.log.write(f"bash: {args[0]}: command not found\n")
            self.log.flush()
            return 127, ""
        return proc.returncode, proc.stdout.decode(errors="surrogateescape").rstrip("\n")

    def isdir(self, path: str) -> bool:
        return os.path.isdir(os.path.join(self.cwd, path))

    def isfile(self, path: str) -> bool:
        return os.path.isfile(os.path.join(self.cwd, path))


def command_env(builder, module: str, variant: str, proxy: str) -> dict[str, str]:
    """The environment of the commands: the driver environment, changed
    by ``proxy(name, env)`` of the environment file for a vcs or
    archive record with a proxy."""
    ctx = builder.ctx(module, variant)
    hook = builder.d.envfile.hook("proxy")
    env = dict(builder.d.base_env())
    env.update(ctx.env.environ())
    if proxy and hook is not None:
        #  proxy(name, env) of the environment file
        hook(proxy, env)
    return env
