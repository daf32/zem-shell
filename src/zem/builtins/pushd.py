import os

from zem.builtins._cwd import change_directory, resolve_target
from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError


def format_stack(context) -> str:
    """Current directory followed by the saved stack, `~`-abbreviated."""
    home = context.variables.get("HOME")
    entries = [context.variables.get("PWD") or os.getcwd(), *context._dir_stack]
    if home:
        entries = [
            "~" + e[len(home):] if e == home or e.startswith(home + os.sep) else e
            for e in entries
        ]
    return " ".join(entries) + "\n"


class PushdCommand(BaseCommand):
    help = "Save the current directory on a stack and change to another"
    usage = "pushd [DIR]"
    examples = [
        "pushd /tmp   - Go to /tmp, remembering where you were",
        "pushd        - Swap the current directory with the top of the stack",
        "popd         - Return to the remembered directory",
    ]

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if len(args) > 1:
            raise ArgumentError(self.name, args, reason="too many arguments")
        current = context.variables.get("PWD") or os.getcwd()
        if not args:
            if not context._dir_stack:
                self._write_err("pushd: no other directory\n", stderr)
                return 1
            target = context._dir_stack.pop(0)
            change_directory(context, self.name, target)
            context._dir_stack.insert(0, current)
        else:
            target = resolve_target(context, self.name, args[0])
            change_directory(context, self.name, target)
            context._dir_stack.insert(0, current)
        self._write(format_stack(context), stdout)
        return 0
