from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class HistoryCommand(BaseCommand):
    help = "Show history"
    usage = "history [-c]"
    tags = ["builtin"]

    def clear(self, context: "ExecutionContext"):
        context.history = []

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if args and args[0] in ("-c", "--clear"):
            self.clear(context)
            if stdout:
                stdout.write("history cleared\n")
            return

        if stdout:
            for i in range(len(context.history)):
                stdout.write(f"{(i + 1):3}  {context.history[i]}\n")
