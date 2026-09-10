from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class ExitCommand(BaseCommand):
    help = "Exit the shell"
    usage = "exit"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        self._write("Closing shell...\n", stdout)
        context.running = False
