from psh.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psh.core.context import ExecutionContext


class ExitCommand(BaseCommand):
    help = "Exit the shell"
    usage = "exit"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if stdout:
            stdout.write("Closing shell...\n")
        context.running = False
