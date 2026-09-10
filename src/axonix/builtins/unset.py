from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class UnsetCommand(BaseCommand):
    name = "unset"
    help = "Unset variable"
    usage = "unset NAME"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        self._require_args(args, min_count=1, error_msg="expected NAME")
        name = args[0]
        context.variables.pop(name, None)
