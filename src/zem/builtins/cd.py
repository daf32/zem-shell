from typing import TYPE_CHECKING

from zem.builtins._cwd import change_directory, resolve_target
from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class CdCommand(BaseCommand):
    help = "Change the shell working directory"
    usage = "cd [directory | - | ~ | ~user]"
    tags = ["builtin"]
    examples = [
        "cd            - Go to home directory",
        "cd /path/to   - Go to specified path",
        "cd -          - Go to previous directory (prints it)",
        "cd ~          - Go to home directory",
        "cd ~alice     - Go to alice's home directory",
        "cd ..         - Go to parent directory",
    ]

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ) -> int:
        if len(args) > 1:
            raise ArgumentError(self.name, args, reason="too many arguments")

        arg = args[0] if args else None
        target = resolve_target(context, self.name, arg)
        new_pwd = change_directory(context, self.name, target)
        if arg == "-":
            self._write(f"{new_pwd}\n", stdout)
        return 0

    def get_completer(self):
        from zem.ui.completers.defaults import DirectoryCompleter
        return DirectoryCompleter()
