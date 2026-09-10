from typing import TYPE_CHECKING

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class UnsetCommand(BaseCommand):
    name = "unset"
    help = "Remove variables"
    usage = "unset [-v] NAME..."

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ) -> int:
        if args and args[0] == "-v":
            args = args[1:]
        elif args and args[0].startswith("-"):
            raise ArgumentError(self.name, args[0], reason="unknown option")
        self._require_args(args, min_count=1, error_msg="expected NAME")

        for name in args:
            if name == "?":
                raise ArgumentError(self.name, name, reason="cannot unset '?'")
            context.unset_var(name)  # unknown names are not an error (bash)
        return 0
