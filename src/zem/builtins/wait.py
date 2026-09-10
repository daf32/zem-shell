import signal

from zem.builtins._jobspec import reject_options
from zem.builtins.base import BaseCommand
from zem.core.jobs import JobError, JobState


class WaitCommand(BaseCommand):
    help = "Wait for background jobs to finish"
    usage = "wait [JOBSPEC|PID...]"
    examples = [
        "wait        - Wait for every background job; exit 0",
        "wait %1     - Wait for job 1; exit with its status",
    ]
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        reject_options(args, self.name)
        shell = getattr(context, "_shell", None)
        if shell is None:
            self._write_err("wait: shell reference not available\n", stderr)
            return 1
        table = context._jobs
        # Jobs that finished since the last check leave the table here, but
        # `wait %N` must still report their status (bash does).
        finished = {job.id: job for job in table.reap() if job.state is JobState.DONE}

        if not args:
            for job in list(table):
                if job.state is JobState.STOPPED:
                    continue  # bash would block forever; skip instead
                shell._wait_job(job, foreground=False)
            return 0

        status = 0
        for spec in args:
            try:
                job = table.get(spec)
            except JobError:
                is_job_number = spec.startswith("%") and spec[1:].isdigit()
                done = finished.get(int(spec[1:])) if is_job_number else None
                if done is None:
                    raise
                status = done.exit_code or 0
                continue
            if job.state is JobState.STOPPED:
                status = 128 + signal.SIGTSTP
                continue
            status = shell._wait_job(job, foreground=False)
        return status
