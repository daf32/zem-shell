from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class SetCommand(BaseCommand):
    name = "set"
    help = "Set a shell variable (or list all variables)"
    usage = "set [-x|--export] NAME [VALUE...] | set -e|--erase NAME... | set"
    examples = [
        "set                 - List all shell variables",
        "set NAME value      - Set a shell-local variable",
        "set -x NAME value   - Set and export to child processes",
        "set -e NAME         - Erase a variable",
    ]

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ) -> int:
        if not args:
            for name in sorted(context.variables):
                self._write(f"{name}={context.variables[name]}\n", stdout)
            return 0

        export = False
        if args[0] in ("-e", "--erase"):
            names = args[1:]
            if not names:
                raise ArgumentError(self.name, args, reason="expected NAME")
            for name in names:
                context.unset_var(name)
            return 0
        if args[0] in ("-x", "--export"):
            export = True
            args = args[1:]
        elif args[0].startswith("-"):
            raise ArgumentError(self.name, args[0], reason="unknown option")

        self._require_args(args, min_count=1, error_msg="expected NAME")
        name = args[0]
        self._validate_identifier(name)
        value = " ".join(args[1:])
        context.set_var(name, value, export=True if export else None)
        return 0
