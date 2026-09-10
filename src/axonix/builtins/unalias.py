from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError


class UnaliasCommand(BaseCommand):
    name = "unalias"
    help = "Remove aliases"
    usage = "unalias NAME... | unalias -a"

    def execute(self, args: list[str], context, stdin=None, stdout=None, stderr=None) -> int:
        if args == ["-a"]:
            context.aliases.clear()
            return 0
        if args and args[0].startswith("-"):
            raise ArgumentError(self.name, args[0], reason="unknown option")
        self._require_args(args, min_count=1, error_msg="expected NAME")

        status = 0
        for name in args:
            if name in context.aliases:
                del context.aliases[name]
            else:
                self._write_err(f"unalias: {name}: not found\n", stderr)
                status = 1
        return status
