from axonix.builtins._jobspec import reject_options, resolve_jobs
from axonix.builtins.base import BaseCommand
from axonix.core.jobs import JobState


class BgCommand(BaseCommand):
    help = "Resume a stopped job in the background"
    usage = "bg [JOBSPEC...]"
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        reject_options(args, self.name)
        status = 0
        for job in resolve_jobs(context._jobs, args, self.name):
            if job.state is JobState.RUNNING:
                self._write_err(f"bg: job {job.id} already in background\n", stderr)
                status = 1
                continue
            context._jobs.resume(job)
            self._write(f"[{job.id}]+ {job.command} &\n", stdout)
        return status
