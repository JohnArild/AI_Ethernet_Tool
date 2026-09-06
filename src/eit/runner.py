"""Subprocess wrapper so tests can capture ip/tc/ethtool without root."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field

log = logging.getLogger("eit.runner")


class CommandError(RuntimeError):
    def __init__(self, argv: list[str], returncode: int, stderr: str):
        self.argv = argv
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"{' '.join(argv)} exited {returncode}: {stderr.strip()}")


@dataclass
class Completed:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


class Runner:
    def run(self, argv: list[str], check: bool = True) -> Completed:
        raise NotImplementedError


class SystemRunner(Runner):
    def run(self, argv: list[str], check: bool = True) -> Completed:
        log.debug("run: %s", " ".join(argv))
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
        )
        completed = Completed(argv, proc.returncode, proc.stdout, proc.stderr)
        if check and proc.returncode != 0:
            raise CommandError(argv, proc.returncode, proc.stderr)
        if proc.returncode != 0:
            log.debug("ignored failure %s: %s", argv, proc.stderr.strip())
        return completed


@dataclass
class RecordingRunner(Runner):
    """Records commands; optional replies keyed by argv tuple prefix."""

    commands: list[list[str]] = field(default_factory=list)
    replies: dict[tuple[str, ...], Completed] = field(default_factory=dict)
    default_stdout: str = ""

    def run(self, argv: list[str], check: bool = True) -> Completed:
        self.commands.append(list(argv))
        key = tuple(argv)
        if key in self.replies:
            completed = self.replies[key]
        else:
            completed = Completed(argv, 0, self.default_stdout, "")
        if check and completed.returncode != 0:
            raise CommandError(argv, completed.returncode, completed.stderr)
        return completed
