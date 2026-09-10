from typing import TYPE_CHECKING

from zem.builtins.base import BaseCommand

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class GetCommand(BaseCommand):
    name = "get"
    help = "Print the value of a variable"
    usage = "get NAME"

    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        self._require_args(args, min_count=1, error_msg="expected NAME")
        name = args[0]
        if name not in context.variables:
            self._write_err(f"get: {name}: variable is not set\n", stderr)
            return 1
        self._write(context.variables[name] + "\n", stdout)
        return 0
