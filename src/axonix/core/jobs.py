"""Job table for background / stopped pipelines (`jobs`, `fg`, `bg`, ...)."""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional

from axonix.errors.base_error import CLIError


class JobError(CLIError):
    exit_code = 1


class JobState(Enum):
    RUNNING = "Running"
    STOPPED = "Stopped"
    DONE = "Done"


@dataclass
class Job:
    id: int
    pgid: int
    command: str
    procs: list[subprocess.Popen]
    state: JobState = JobState.RUNNING
    notified: bool = False
    exit_code: Optional[int] = None
    #: Exit codes seen so far per process index (filled by waits).
    _codes: dict[int, int] = field(default_factory=dict)

    @property
    def last_code(self) -> int:
        """Exit code of the last stage (bash semantics), 0 if unknown."""
        return self._codes.get(len(self.procs) - 1, 0)


def wait_process(proc: subprocess.Popen, *, blocking: bool = True) -> tuple[str, int]:
    """Wait on ``proc`` with ``WUNTRACED``.

    Returns ``(state, value)`` where state is ``"exited"`` (value = exit
    code), ``"signaled"`` (value = signal number), ``"stopped"`` (value =
    stop signal) or ``"running"`` (only when ``blocking=False``). The
    Popen's ``returncode`` is set on exit so it never gets reaped twice.
    """
    if proc.returncode is not None:
        code = proc.returncode
        return ("signaled", -code) if code < 0 else ("exited", code)
    flags = os.WUNTRACED | (0 if blocking else os.WNOHANG)
    try:
        pid, status = os.waitpid(proc.pid, flags)
    except ChildProcessError:
        # Someone else (Popen.poll) reaped it already.
        proc.poll()
        code = proc.returncode if proc.returncode is not None else 0
        return ("signaled", -code) if code < 0 else ("exited", code)
    if pid == 0:
        return ("running", 0)
    if os.WIFSTOPPED(status):
        return ("stopped", os.WSTOPSIG(status))
    if os.WIFSIGNALED(status):
        proc.returncode = -os.WTERMSIG(status)
        return ("signaled", os.WTERMSIG(status))
    proc.returncode = os.WEXITSTATUS(status)
    return ("exited", proc.returncode)


def exit_code_from(state: str, value: int) -> int:
    if state == "exited":
        return value
    if state == "signaled":
        return 128 + value
    if state == "stopped":
        return 128 + value
    return 0


class JobTable:
    def __init__(self) -> None:
        self._jobs: dict[int, Job] = {}
        self._next_id = 1
        self._recent: list[int] = []  # most recent last; drives %+ / %-

    # -- bookkeeping ---------------------------------------------------------

    def add(self, pgid: int, command: str, procs: list[subprocess.Popen],
            state: JobState = JobState.RUNNING) -> Job:
        job = Job(self._next_id, pgid, command, procs, state)
        self._jobs[job.id] = job
        self._next_id += 1
        self._touch(job)
        return job

    def _touch(self, job: Job) -> None:
        if job.id in self._recent:
            self._recent.remove(job.id)
        self._recent.append(job.id)

    def remove(self, job: Job) -> None:
        self._jobs.pop(job.id, None)
        if job.id in self._recent:
            self._recent.remove(job.id)
        if not self._jobs:
            self._next_id = 1

    def __iter__(self) -> Iterator[Job]:
        return iter(sorted(self._jobs.values(), key=lambda j: j.id))

    def __len__(self) -> int:
        return len(self._jobs)

    def __bool__(self) -> bool:
        return bool(self._jobs)

    def stopped(self) -> list[Job]:
        return [j for j in self if j.state is JobState.STOPPED]

    # -- lookup ---------------------------------------------------------------

    def current(self) -> Optional[Job]:
        """`%+`: the most recently stopped job, else the most recent job."""
        for jid in reversed(self._recent):
            if self._jobs[jid].state is JobState.STOPPED:
                return self._jobs[jid]
        return self._jobs[self._recent[-1]] if self._recent else None

    def previous(self) -> Optional[Job]:
        """`%-`: the job that `%+` would become if the current one went away."""
        cur = self.current()
        for jid in reversed(self._recent):
            if cur is None or jid != cur.id:
                return self._jobs[jid]
        return None

    def get(self, spec: Optional[str]) -> Job:
        """Resolve ``%N``, ``%%``/``%+``, ``%-``, ``%prefix``, a pid, or
        ``None`` (current job). Raises :class:`JobError`."""
        if spec is None or spec in ("%%", "%+", "%"):
            job = self.current()
            if job is None:
                raise JobError("no current job")
            return job
        if spec == "%-":
            job = self.previous()
            if job is None:
                raise JobError("no previous job")
            return job
        if spec.startswith("%"):
            body = spec[1:]
            if body.isdigit():
                job = self._jobs.get(int(body))
                if job is None:
                    raise JobError(f"{spec}: no such job")
                return job
            matches = [j for j in self if j.command.startswith(body)]
            if len(matches) == 1:
                return matches[0]
            if not matches:
                raise JobError(f"{spec}: no such job")
            raise JobError(f"{spec}: ambiguous job spec")
        if spec.isdigit():
            pid = int(spec)
            for job in self:
                if job.pgid == pid or any(p.pid == pid for p in job.procs):
                    return job
            raise JobError(f"{spec}: no such job")
        raise JobError(f"{spec}: no such job")

    # -- state --------------------------------------------------------------

    def reap(self) -> list[Job]:
        """Poll every job; return those whose state changed since last report.

        Finished jobs are removed from the table after being returned (the
        caller prints the `Done` notice).
        """
        changed: list[Job] = []
        for job in list(self):
            before = job.state
            self.refresh(job)
            if job.state is not before and not job.notified:
                changed.append(job)
                job.notified = job.state is not JobState.DONE
            if job.state is JobState.DONE:
                if job not in changed and not job.notified:
                    changed.append(job)
                self.remove(job)
        return changed

    def refresh(self, job: Job) -> None:
        """Non-blocking update of ``job.state`` from the kernel."""
        any_stopped = False
        all_done = True
        for idx, proc in enumerate(job.procs):
            state, value = wait_process(proc, blocking=False)
            if state == "stopped":
                any_stopped = True
                all_done = False
            elif state == "running":
                all_done = False
            else:
                job._codes[idx] = exit_code_from(state, value)
        if all_done:
            job.state = JobState.DONE
            job.exit_code = job.last_code
        elif any_stopped:
            if job.state is not JobState.STOPPED:
                job.state = JobState.STOPPED
                job.notified = False
                self._touch(job)
        # A job we only know as STOPPED stays so until `bg`/`fg` continue it.

    def signal(self, job: Job, sig: int) -> None:
        os.killpg(job.pgid, sig)

    def resume(self, job: Job) -> None:
        self.signal(job, signal.SIGCONT)
        job.state = JobState.RUNNING
        job.notified = False
        self._touch(job)


def format_notice(job: Job, marker: str = " ") -> str:
    """bash-style status line: ``[1]+  Stopped                 sleep 5``."""
    if job.state is JobState.DONE:
        code = job.exit_code or 0
        status = "Done" if code == 0 else f"Exit {code}"
    else:
        status = job.state.value
    return f"[{job.id}]{marker} {status:<23} {job.command}"
