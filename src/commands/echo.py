from src.commands.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.context import ExecutionContext


class EchoCommand(BaseCommand):
    help = "Print arguments"
    usage = "echo [text...]"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if stdout:
            stdout.write(" ".join(args) + "\n")
