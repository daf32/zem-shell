from zem.builtins._jobspec import reject_options, resolve_jobs
from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError


class FgCommand(BaseCommand):
    help = "Bring a job to the foreground"
    usage = "fg [JOBSPEC]"
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        reject_options(args, self.name)
        if len(args) > 1:
            raise ArgumentError(self.name, args, reason="too many arguments")
        shell = getattr(context, "_shell", None)
        if shell is None:
            self._write_err("fg: shell reference not available\n", stderr)
            return 1
        job = resolve_jobs(context._jobs, args, self.name)[0]
        self._write(f"{job.command}\n", stdout)
        context._jobs.resume(job)
        return shell._wait_job(job, foreground=True)
