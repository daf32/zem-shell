import shutil

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError


def describe(name: str, context) -> tuple[str, str] | None:
    """Return ``(kind, detail)`` for a command name, or ``None`` if unknown.

    Lookup order matches execution order: alias, builtin, then PATH.
    """
    if name in context.aliases:
        return "alias", context.aliases[name]
    if name in context.commands:
        return "builtin", ""
    path = shutil.which(name)
    if path:
        return "file", path
    return None


class TypeCommand(BaseCommand):
    help = "Describe how a command name would be interpreted"
    usage = "type [-t] NAME..."
    examples = [
        "type ls        - `ls is /bin/ls`",
        "type ll        - `ll is an alias for ls -la`",
        "type -t cd     - Just the kind: alias, builtin or file",
    ]

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        kind_only = False
        if args and args[0] == "-t":
            kind_only = True
            args = args[1:]
        elif args and args[0].startswith("-"):
            raise ArgumentError(self.name, args[0], reason="unknown option")
        self._require_args(args, min_count=1, error_msg="expected NAME")

        status = 0
        for name in args:
            found = describe(name, context)
            if found is None:
                self._write_err(f"type: {name}: not found\n", stderr)
                status = 1
                continue
            kind, detail = found
            if kind_only:
                self._write(f"{kind}\n", stdout)
            elif kind == "alias":
                self._write(f"{name} is an alias for {detail}\n", stdout)
            elif kind == "builtin":
                self._write(f"{name} is a shell builtin\n", stdout)
            else:
                self._write(f"{name} is {detail}\n", stdout)
        return status
