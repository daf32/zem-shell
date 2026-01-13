from typing import TYPE_CHECKING
from src.commands.base import BaseCommand
from src.errors.input import ArgumentError

if TYPE_CHECKING:
    from src.context import ExecutionContext

class GetCommand(BaseCommand):
    name = "get"
    help = "Print variable value"
    usage = "get NAME"

    def execute(self, args: list[str], context: 'ExecutionContext'):
        if not args:
            raise ArgumentError(self.name, '', "expected NAME")
        name = args[0]
        if not context.variables.get(name):
            raise ArgumentError(self.name, name, f"variable '{name}' is not set")
        print(context.variables.get(name))