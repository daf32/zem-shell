from typing import TYPE_CHECKING

from zem.builtins.base import BaseCommand
from zem.core.jobs import format_notice
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class ExitCommand(BaseCommand):
    help = "Exit the shell"
    usage = "exit [n]"
    examples = [
        "exit      - Exit with the status of the last command",
        "exit 3    - Exit with status 3",
    ]
    main_thread_only = True

    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        # `reap` hands back the jobs whose state changed; they are the
        # "Done" and "Exit N" lines the user is owed, and dropping them
        # here meant a job that finished while you were typing `exit` was
        # never reported at all.
        current = context._jobs.current()
        for job in context._jobs.reap():
            marker = "+" if job is current else " "
            self._write_err(format_notice(job, marker) + "\n", stderr)

        if context._jobs.stopped() and not context._exit_warned:
            context._exit_warned = True
            self._write_err("There are stopped jobs.\n", stderr)
            return 1
        if len(args) > 1:
            raise ArgumentError(self.name, args, reason="too many arguments")
        if args:
            try:
                status = int(args[0])
            except ValueError:
                raise ArgumentError(
                    self.name, args[0], reason="numeric argument required"
                ) from None
        else:
            status = context.last_exit_code

        context.exit_status = status & 0xFF
        context.running = False
        return context.exit_status
