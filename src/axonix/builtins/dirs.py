from axonix.builtins.base import BaseCommand
from axonix.builtins.pushd import format_stack
from axonix.errors.input_error import ArgumentError


class DirsCommand(BaseCommand):
    help = "Show the directory stack"
    usage = "dirs [-c]"

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if args == ["-c"]:
            context._dir_stack.clear()
            return 0
        if args:
            raise ArgumentError(self.name, args, reason="unknown option")
        self._write(format_stack(context), stdout)
        return 0
