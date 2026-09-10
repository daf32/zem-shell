from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class SetCommand(BaseCommand):
    name = "set"
    help = "Set variable"
    usage = "set NAME VALUE..."

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ) -> None:
        self._require_args(args, min_count=1, error_msg="expected NAME and VALUE")
        
        name = args[0]
        self._validate_identifier(name)
        
        value = " ".join(args[1:]) if len(args) > 1 else ""
        context.variables[name] = value
