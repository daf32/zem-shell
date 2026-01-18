from psh.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psh.core.context import ExecutionContext


class HistoryCommand(BaseCommand):
    help = "Show history"
    usage = "history"

    def clear(self, context: "ExecutionContext"):
        context.history = []

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if stdout:
            for i in range(len(context.history)):
                stdout.write(f"{(i + 1):3}  {context.history[i]}\n")
