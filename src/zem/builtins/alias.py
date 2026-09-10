from zem.builtins._quote import sh_quote
from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError


class AliasCommand(BaseCommand):
    name = "alias"
    help = "Create or list aliases"
    usage = "alias [-p] [name[=value] ...]"
    examples = [
        "alias                  - List aliases (re-sourceable)",
        "alias ll='ls -la'      - Define an alias",
        "alias ll               - Show one alias",
        "alias gc='git commit -m $1'  - Parameterised alias",
    ]

    def _print_one(self, name: str, value: str, stdout) -> None:
        self._write(f"alias {name}={sh_quote(value)}\n", stdout)

    def execute(self, args: list[str], context, stdin=None, stdout=None, stderr=None) -> int:
        if args and args[0] == "-p":
            args = args[1:]
        if not args:
            for name, value in sorted(context.aliases.items()):
                self._print_one(name, value, stdout)
            return 0

        status = 0
        for arg in args:
            name, sep, value = arg.partition("=")
            if not name:
                raise ArgumentError(self.name, arg, reason="empty alias name")
            if sep:
                # The parser has already stripped quotes from `value`.
                context.aliases[name] = value
            elif name in context.aliases:
                self._print_one(name, context.aliases[name], stdout)
            else:
                self._write_err(f"alias: {name}: not found\n", stderr)
                status = 1
        return status
