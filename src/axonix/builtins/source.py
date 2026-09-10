import os

from axonix.builtins.base import BaseCommand


class SourceCommand(BaseCommand):
    help = "Run commands from a file in the current shell"
    usage = "source FILE | . FILE"
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        self._require_args(args, min_count=1, error_msg="expected FILE")
        path = os.path.expanduser(args[0])
        shell = getattr(context, "_shell", None)
        if shell is None:
            self._write_err(f"{self.name}: shell reference not available\n", stderr)
            return 1
        if not os.path.isfile(path):
            self._write_err(f"{self.name}: {args[0]}: No such file\n", stderr)
            return 1
        return shell._run_script_file(path)


class DotCommand(SourceCommand):
    name = "."
    help = "Run commands from a file in the current shell (same as source)"
    usage = ". FILE"
