from typing import TYPE_CHECKING
from src.commands.base import BaseCommand

if TYPE_CHECKING:
    from src.context import ExecutionContext

class HistoryCommand(BaseCommand):
    help = "Show history"
    usage = f"history\n{'   --clear':10} - clear history"

    def clear(self, context: 'ExecutionContext'):
            context.history = []

    def execute(self, args: list[str], context: 'ExecutionContext'):
        if "--clear" in args:
            self.clear(context)
        print(f"History: {context.history}")