import os
from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext

class PwdCommand(BaseCommand):
    help = "Print the current working directory"
    usage = "pwd"

    def execute(self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None):
        self._write(os.getcwd() + "\n", stdout)
