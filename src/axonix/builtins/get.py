from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class GetCommand(BaseCommand):
    name = "get"
    help = "Print variable value"
    usage = "get NAME"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        self._require_args(args, min_count=1, error_msg="expected NAME")
        
        name = args[0]
        if not context.variables.get(name):
            raise ArgumentError(self.name, name, f"variable '{name}' is not set")
        self._write(str(context.variables.get(name)) + "\n", stdout)
