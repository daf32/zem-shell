from zem.builtins._jobspec import reject_options
from zem.builtins.base import BaseCommand
from zem.core.jobs import format_notice


class JobsCommand(BaseCommand):
    help = "List background and stopped jobs"
    usage = "jobs [-l|-p] [JOBSPEC...]"
    examples = [
        "jobs        - `[1]+  Running   sleep 30 &`",
        "jobs -l     - Also show the process group id",
        "jobs -p     - Only the process group ids",
    ]
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        reject_options(args, self.name, ("-l", "-p"))
        show_pid = "-l" in args
        only_pid = "-p" in args
        specs = [a for a in args if not a.startswith("-")]

        table = context._jobs
        # Report finished jobs first (they leave the table), like bash.
        for job in table.reap():
            self._write(format_notice(job, " ") + "\n", stdout)

        jobs = list(table) if not specs else [table.get(s) for s in specs]
        current = table.current()
        previous = table.previous()
        for job in jobs:
            if only_pid:
                self._write(f"{job.pgid}\n", stdout)
                continue
            marker = "+" if job is current else "-" if job is previous else " "
            line = format_notice(job, marker)
            if show_pid:
                line = f"[{job.id}]{marker} {job.pgid} {line[len(f'[{job.id}]{marker} '):]}"
            self._write(line + "\n", stdout)
        return 0
