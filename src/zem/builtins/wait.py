from zem.builtins._jobspec import reject_options
from zem.builtins.base import BaseCommand
from zem.core.jobs import JobState


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
        table.reap()

        if not args:
            for job in list(table):
                if job.state is JobState.STOPPED:
                    continue  # bash would block forever; skip instead
                shell._wait_job(job, foreground=False)
            return 0

        status = 0
        for spec in args:
            job = table.get(spec)
            if job.state is JobState.STOPPED:
                status = 128 + __import__("signal").SIGTSTP
                continue
            status = shell._wait_job(job, foreground=False)
        return status
