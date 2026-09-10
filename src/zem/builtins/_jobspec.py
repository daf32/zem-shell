"""Shared helpers for the job-control builtins."""

from zem.core.jobs import Job, JobTable
from zem.errors.input_error import ArgumentError


def resolve_jobs(table: JobTable, specs: list[str], cmd: str) -> list[Job]:
    """Resolve job specs (or the current job when ``specs`` is empty)."""
    table.reap()
    if not specs:
        return [table.get(None)]
    return [table.get(spec) for spec in specs]


def reject_options(args: list[str], cmd: str, allowed: tuple[str, ...] = ()) -> None:
    for arg in args:
        if arg.startswith("-") and arg not in allowed and not arg[1:].isdigit():
            raise ArgumentError(cmd, arg, reason="unknown option")
