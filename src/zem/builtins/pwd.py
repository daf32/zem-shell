import os
from typing import TYPE_CHECKING

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class PwdCommand(BaseCommand):
    help = "Print the current working directory"
    usage = "pwd [-L|-P]"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ) -> int:
        physical = False
        for arg in args:
            if arg == "-P":
                physical = True
            elif arg == "-L":
                physical = False
            else:
                raise ArgumentError(self.name, arg, reason="unknown option")

        # Logical: prefer $PWD when it still names the current directory
        # (keeps symlinked paths as the user typed them).
        logical = context.variables.get("PWD")
        cwd = os.getcwd()
        if not physical and logical and os.path.realpath(logical) == cwd:
            self._write(logical + "\n", stdout)
        else:
            self._write(cwd + "\n", stdout)
        return 0
