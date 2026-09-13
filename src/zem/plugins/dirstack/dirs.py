from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError
from zem.plugins.dirstack.pushd import format_stack


class DirsCommand(BaseCommand):
    name = "dirs"
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
