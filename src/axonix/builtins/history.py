from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class HistoryCommand(BaseCommand):
    help = "Show or edit command history"
    usage = "history [N] [PATTERN] | history -c | history -d N"
    tags = ["builtin"]
    examples = [
        "history          - Show all history",
        "history 10       - Show last 10 commands",
        "history git      - Show commands containing 'git'",
        "history -c       - Clear history (memory and file)",
        "history -d 3     - Delete entry number 3 (this session)",
    ]

    def clear(self, context: "ExecutionContext") -> None:
        """Clear in-memory history and, when available, the history file."""
        context.history = []
        shell = getattr(context, "_shell", None)
        session = getattr(shell, "session", None)
        file_history = getattr(session, "history", None)
        if hasattr(file_history, "clear"):
            file_history.clear()

    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        if args and args[0] in ("-c", "--clear"):
            if len(args) > 1:
                raise ArgumentError(self.name, args, reason="-c takes no arguments")
            self.clear(context)
            return 0

        if args and args[0] in ("-d", "--delete"):
            if len(args) != 2 or not args[1].isdigit():
                raise ArgumentError(self.name, args, reason="expected -d N")
            index = int(args[1])
            if not 1 <= index <= len(context.history):
                self._write_err(f"history: {index}: history position out of range\n", stderr)
                return 1
            del context.history[index - 1]
            return 0

        limit = None
        pattern = None
        for arg in args:
            if arg.startswith("-"):
                raise ArgumentError(self.name, arg, reason="unknown option")
            if arg.isdigit() and limit is None:
                limit = int(arg)
            elif pattern is None:
                pattern = arg
            else:
                raise ArgumentError(self.name, args, reason="too many arguments")

        entries = [(i + 1, cmd) for i, cmd in enumerate(context.history)]
        if pattern:
            entries = [(i, cmd) for i, cmd in entries if pattern.lower() in cmd.lower()]
        if limit is not None:
            entries = entries[-limit:] if limit else []

        if not entries:
            return 0

        path_color = "#00ffff"
        cmd_color = "#ffffff"
        shell = getattr(context, "_shell", None)
        if shell is not None:
            path_color = shell.config.colors.path
            cmd_color = shell.config.colors.command

        # `_print_colored` degrades to plain text in pipes/redirects.
        for idx, cmd in entries:
            self._print_colored([(path_color, f"{idx:5}  "), (cmd_color, cmd)], stdout)
        return 0
