import os
from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class ExportCommand(BaseCommand):
    name = "export"
    usage = "export NAME=VALUE"
    help = "Export a variable to the environment"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if not args:
            self._write("\n".join(f"{k}={v}" for k, v in os.environ.items()) + "\n", stdout)
            return

        for arg in args:
            if "=" not in arg:
                raise ArgumentError(
                    self.name, arg, reason="invalid format, use NAME=VALUE"
                )

            name, value = arg.split("=", 1)
            context.variables[name] = value
            os.environ[name] = value
            # Sync to context (though it's already updated above)
            # This ensures consistency
            context.sync_to_environment()