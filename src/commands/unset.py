from typing import TYPE_CHECKING
from src.commands.base import BaseCommand
from src.errors.input import ArgumentError

if TYPE_CHECKING:
    from src.context import ExecutionContext

class UnsetCommand(BaseCommand):
    name = "unset"
    help = "Unset variable"
    usage = "unset NAME"

    def execute(self, args: list[str], context: 'ExecutionContext'):
        if not args:
            raise ArgumentError(self.name, '', "expected NAME")
        name = args[0]
        context.variables.pop(name, None)