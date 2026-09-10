import os
import shutil

from axonix.builtins.base import BaseCommand


class ExecCommand(BaseCommand):
    help = "Replace the shell with the given command"
    usage = "exec CMD [ARG...]"
    examples = [
        "exec bash    - Hand this terminal over to bash",
        "exec         - No-op (fd-only exec is not supported)",
    ]
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if not args:
            return 0
        cmd = args[0]
        path = cmd if "/" in cmd else shutil.which(cmd, path=context.variables.get("PATH"))
        if not path or not os.access(path, os.X_OK):
            self._write_err(f"exec: {cmd}: not found\n", stderr)
            return 127

        shell = getattr(context, "_shell", None)
        if shell is not None:
            shell._restore_terminal()
            shell.executor.cleanup_processes()
        try:
            os.execve(path, [cmd, *args[1:]], context.child_env())
        except OSError as e:
            self._write_err(f"exec: {cmd}: {e.strerror}\n", stderr)
            return 126
        return 0  # unreachable
