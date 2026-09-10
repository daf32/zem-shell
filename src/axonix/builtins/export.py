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
            env = context.child_env()
            self._write("".join(f"{k}={env[k]}\n" for k in sorted(env)), stdout)
            return 0

        for arg in args:
            if "=" not in arg:
                raise ArgumentError(
                    self.name, arg, reason="invalid format, use NAME=VALUE"
                )

            name, value = arg.split("=", 1)
            context.set_var(name, value, export=True)
        return 0