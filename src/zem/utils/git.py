"""What the prompt says about the repository you are standing in.

One `git status --porcelain=v2 --branch` per prompt answers everything the
prompt needs -- the branch, how far it is from its upstream, whether the
tree is dirty -- where this used to run up to six commands, each with its
own half-second timeout. The call is isolated the way the completion
helpers are (see `zem.hints.sources`): its own session, no stdin, no
index lock, so a prompt can neither hang on the terminal nor fight the
git command the user is running in it.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from typing import Optional, Tuple

log = logging.getLogger(__name__)

#: Long enough for a cold cache on a large repository, short enough that a
#: prompt on a stalled network filesystem still appears. Override per
#: repository with `prompt.modules.git.timeout_ms`.
DEFAULT_TIMEOUT_MS = 1000

#: `git status` prints one line per changed or untracked entry; we only
#: need to know whether there is any. Parsing stops once the headers are
#: read and one entry has been seen, and this caps what we hold anyway.
MAX_OUTPUT_BYTES = 1_000_000

#: Porcelain v2 header lines we read; everything else on a `#` line is
#: another header we do not need.
_HEAD = "# branch.head "
_OID = "# branch.oid "
_AB = "# branch.ab "


@dataclass(frozen=True)
class GitStatus:
    """The parsed answer of one `git status --porcelain=v2 --branch`."""

    branch: str
    ahead: int = 0
    behind: int = 0
    dirty: bool = False

    @property
    def symbols(self) -> str:
        """`*` dirty, `+` ahead, `-` behind -- in that order."""
        return (
            ("*" if self.dirty else "")
            + ("+" if self.ahead else "")
            + ("-" if self.behind else "")
        )


def parse_status(text: str) -> Optional[GitStatus]:
    """Turn porcelain v2 output into a :class:`GitStatus`.

    Returns ``None`` when the output carries no branch header at all,
    which is what a git too old for `--porcelain=v2` would produce.
    """
    branch = ""
    oid = ""
    ahead = behind = 0
    dirty = False

    for line in text.splitlines():
        if not line.startswith("#"):
            # `1`/`2` changed, `u` unmerged, `?` untracked: any of them
            # means the tree is not clean, and one is enough to know.
            dirty = True
            if branch:
                break
            continue
        if line.startswith(_HEAD):
            branch = line[len(_HEAD):].strip()
        elif line.startswith(_OID):
            oid = line[len(_OID):].strip()
        elif line.startswith(_AB):
            ahead, behind = _ahead_behind(line[len(_AB):])

    if not branch:
        return None
    if branch == "(detached)":
        # `rev-parse --abbrev-ref HEAD` used to answer a literal "HEAD"
        # here; the commit you are on is the useful thing to show.
        branch = oid[:7] if oid and oid != "(initial)" else "detached"
    return GitStatus(branch=branch, ahead=ahead, behind=behind, dirty=dirty)


def _ahead_behind(field: str) -> Tuple[int, int]:
    """Read the `+N -M` of a `# branch.ab` header."""
    ahead = behind = 0
    for part in field.split():
        try:
            value = int(part[1:])
        except ValueError:
            continue
        if part[0] == "+":
            ahead = value
        elif part[0] == "-":
            behind = value
    return ahead, behind


def _child_env() -> dict:
    """A git that cannot lock, translate, page or ask the user anything."""
    return {
        **os.environ,
        # Never let a prompt touch .git/index.lock: the user may be running
        # a git command in this very repository.
        "GIT_OPTIONAL_LOCKS": "0",
        "LC_ALL": "C",
        # A helper (fsmonitor, credentials) must not stop to ask: there is
        # nobody at the other end of a prompt being drawn.
        "GIT_TERMINAL_PROMPT": "0",
    }


def git_status(cwd: Optional[str] = None, timeout_ms: Optional[int] = None) -> Optional[GitStatus]:
    """Status of the repository at ``cwd``, or ``None`` if there is none.

    Never raises: a missing git, a timeout, a directory that has been
    removed and a repository git refuses to read all mean "no repository"
    as far as the prompt is concerned.
    """
    timeout = (timeout_ms or DEFAULT_TIMEOUT_MS) / 1000
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v2", "--branch"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            # The shell hands the terminal to foreground process groups
            # with `tcsetpgrp`; a git helper that joined this one could
            # take the terminal and hang the prompt.
            start_new_session=True,
            env=_child_env(),
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        log.debug("git status in %r failed: %s", cwd, exc)
        return None
    if proc.returncode != 0:
        return None  # not a repository, or git could not read it
    return parse_status(proc.stdout[:MAX_OUTPUT_BYTES])


def get_git_info(
    cwd: Optional[str] = None, timeout_ms: Optional[int] = None
) -> Optional[Tuple[str, str]]:
    """``(branch, symbols)`` for the prompt, or ``None`` outside a repository.

    ``symbols`` is ``*`` when the tree is dirty, ``+`` when the branch is
    ahead of its upstream and ``-`` when it is behind, in that order.
    """
    status = git_status(cwd, timeout_ms)
    if status is None:
        return None
    return status.branch, status.symbols
