from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class EchoCommand(BaseCommand):
    help = "Print arguments"
    usage = "echo [text...]"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        self._write(" ".join(args) + "\n", stdout)
