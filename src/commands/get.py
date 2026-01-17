from src.commands.base import BaseCommand
from src.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.context import ExecutionContext


class GetCommand(BaseCommand):
    name = "get"
    help = "Print variable value"
    usage = "get NAME"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if not args:
            raise ArgumentError(self.name, "", "expected NAME")
        name = args[0]
        if not context.variables.get(name):
            raise ArgumentError(self.name, name, f"variable '{name}' is not set")
        if stdout:
            stdout.write(str(context.variables.get(name)) + "\n")
