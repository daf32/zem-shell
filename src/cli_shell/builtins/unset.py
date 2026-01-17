from cli_shell.builtins.base import BaseCommand
from cli_shell.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli_shell.core.context import ExecutionContext


class UnsetCommand(BaseCommand):
    name = "unset"
    help = "Unset variable"
    usage = "unset NAME"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if not args:
            raise ArgumentError(self.name, "", "expected NAME")
        name = args[0]
        context.variables.pop(name, None)
