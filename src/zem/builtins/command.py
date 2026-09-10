from zem.builtins.base import BaseCommand
from zem.builtins.type import describe
from zem.errors.input_error import ArgumentError


class CommandCommand(BaseCommand):
    """`command -v/-V NAME` lives here; plain `command CMD ARGS...` is
    rewritten by the parser into a pipeline stage flagged `force_external`,
    so builtins and aliases are bypassed like in bash."""

    name = "command"
    help = "Run a command bypassing aliases and builtins, or describe it"
    usage = "command [-v|-V] NAME... | command CMD [ARGS...]"
    examples = [
        "command ls          - Run /bin/ls even if `ls` is an alias",
        "command -v git      - Print the path (or name for builtins/aliases)",
        "command -V cd       - Verbose description, like `type`",
    ]

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if not args:
            return 0
        if args[0] not in ("-v", "-V"):
            # Only reachable if the parser rewrite was bypassed.
            raise ArgumentError(self.name, args[0], reason="unknown option")
        verbose = args[0] == "-V"
        names = args[1:]
        self._require_args(names, min_count=1, error_msg="expected NAME")

        status = 0
        for name in names:
            found = describe(name, context)
            if found is None:
                status = 1
                if verbose:
                    self._write_err(f"command: {name}: not found\n", stderr)
                continue
            kind, detail = found
            if verbose:
                if kind == "alias":
                    self._write(f"{name} is an alias for {detail}\n", stdout)
                elif kind == "builtin":
                    self._write(f"{name} is a shell builtin\n", stdout)
                else:
                    self._write(f"{name} is {detail}\n", stdout)
            else:
                self._write((detail if kind == "file" else name) + "\n", stdout)
        return status
