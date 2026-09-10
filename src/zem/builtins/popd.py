from zem.builtins._cwd import change_directory
from zem.builtins.base import BaseCommand
from zem.builtins.pushd import format_stack
from zem.errors.input_error import ArgumentError


class PopdCommand(BaseCommand):
    help = "Change to the directory on top of the stack and remove it"
    usage = "popd"

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if args:
            raise ArgumentError(self.name, args, reason="too many arguments")
        if not context._dir_stack:
            self._write_err("popd: directory stack empty\n", stderr)
            return 1
        target = context._dir_stack.pop(0)
        change_directory(context, self.name, target)
        self._write(format_stack(context), stdout)
        return 0
