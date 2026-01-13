from typing import TYPE_CHECKING
from src.commands.base import BaseCommand
from src.errors.input import ArgumentError

if TYPE_CHECKING:
    from src.context import ExecutionContext

class AddCommand(BaseCommand):
    help = "Add numbers"
    usage = "add n1 n2 [n3 ...]"

    def execute(self, args: list[str], context: 'ExecutionContext'):
        if not args:
            raise ArgumentError(self.name, args, reason="expected at least one number")
        try:
            numbers = [float(a) for a in args]
            print(sum(numbers))
        except ValueError:
            raise ArgumentError(self.name, args)