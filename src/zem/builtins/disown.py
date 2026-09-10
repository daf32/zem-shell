from zem.builtins._jobspec import reject_options, resolve_jobs
from zem.builtins.base import BaseCommand


class DisownCommand(BaseCommand):
    help = "Remove jobs from the table (they won't get SIGHUP on exit)"
    usage = "disown [-a] [JOBSPEC...]"
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        reject_options(args, self.name, ("-a",))
        table = context._jobs
        if "-a" in args:
            for job in list(table):
                table.remove(job)
            return 0
        for job in resolve_jobs(table, args, self.name):
            table.remove(job)
        return 0
