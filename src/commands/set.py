from typing import TYPE_CHECKING, List
from src.commands.base import BaseCommand
from src.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from src.context import ExecutionContext

class SetCommand(BaseCommand):
    name = "set"
    help = "Set variable"
    usage = "set NAME VALUE..."

    def execute(self, args: List[str], context: 'ExecutionContext', stdin=None, stdout=None) -> None:
        if not args:
            raise ArgumentError(self.name, args, "expected NAME and VALUE")
        name = args[0]
        if not name.isidentifier():
            raise ArgumentError(self.name, args, "variable name must be a valid identifier (letters, digits, underscore, not starting with digit)")
        value = " ".join(args[1:]) if len(args) > 1 else ""
        context.variables[name] = value