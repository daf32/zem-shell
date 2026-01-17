import os
from src.commands.base import BaseCommand
from src.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.context import ExecutionContext


class ExportCommand(BaseCommand):
    name = "export"
    usage = "export NAME=VALUE"
    help = "Export a variable to the environment"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if not args:
            stdout.write("\n".join(f"{k}={v}" for k, v in os.environ.items()) + "\n")   
            return

        for arg in args:
            if "=" not in arg:
                raise ArgumentError(
                    self.name, arg, reason="invalid format, use NAME=VALUE"
                )

            name, value = arg.split("=", 1)
            context.variables[name] = value
            os.environ[name] = value
