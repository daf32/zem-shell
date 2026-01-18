from typing import TYPE_CHECKING
from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class AddCommand(BaseCommand):
    help = "Add numbers"
    usage = "add n1 n2 [n3 ...]"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        numbers = []

        try:
            numbers.extend([float(a) for a in args])
        except ValueError:
            raise ArgumentError(self.name, args, reason="arguments must be numbers")

        if stdin and not stdin.isatty():
            try:
                content = stdin.read()
                for token in content.split():
                    numbers.append(float(token))
            except ValueError:
                pass

        if not numbers:
            raise ArgumentError(
                self.name,
                args,
                reason="expected at least one number (in args or stdin)",
            )

        try:
            if stdout:
                stdout.write(str(sum(numbers)) + "\n")
        except ValueError:
            raise ArgumentError(self.name, args)
