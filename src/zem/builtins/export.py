from typing import TYPE_CHECKING

from zem.builtins._quote import sh_quote
from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class ExportCommand(BaseCommand):
    name = "export"
    usage = "export [-p] | export NAME[=VALUE]... | export -n NAME..."
    help = "Export variables to the environment of child processes"
    examples = [
        "export              - List exported variables",
        "export FOO=bar      - Set and export FOO",
        "export FOO          - Export an existing shell variable",
        "export -n FOO       - Stop exporting FOO (value is kept)",
    ]

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ) -> int:
        if not args or args == ["-p"]:
            env = context.child_env()
            for name in sorted(env):
                self._write(f"export {name}={sh_quote(env[name])}\n", stdout)
            return 0

        unexport = False
        if args[0] == "-n":
            unexport = True
            args = args[1:]
            if not args:
                raise ArgumentError(self.name, "-n", reason="expected NAME")
        elif args[0].startswith("-"):
            raise ArgumentError(self.name, args[0], reason="unknown option")

        for arg in args:
            name, sep, value = arg.partition("=")
            self._validate_identifier(name)
            if unexport:
                context.unexport_var(name)
            elif sep:
                context.set_var(name, value, export=True)
            else:
                context.export_var(name)
        return 0
