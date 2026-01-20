from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class HistoryCommand(BaseCommand):
    help = "Show history"
    usage = "history [-c]"
    tags = ["builtin"]

    def clear(self, context: "ExecutionContext"):
        context.history = []

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        if args and args[0] in ("-c", "--clear"):
            self.clear(context)
            self._write("history cleared\n", stdout)
            return

        # Handle search or limit
        search_term = None
        limit = None
        
        for arg in args:
            if arg.isdigit():
                limit = int(arg)
            else:
                search_term = arg

        history = context.history
        
        # Filter by search term
        if search_term:
            filtered_history = []
            for i, cmd in enumerate(history):
                if search_term in cmd:
                    filtered_history.append((i + 1, cmd))
            entries = filtered_history
        else:
            entries = [(i + 1, cmd) for i, cmd in enumerate(history)]

        # Apply limit (last N)
        if limit and limit < len(entries):
            entries = entries[-limit:]

        # Use colors for formatting if available
        path_color = context._shell.config.colors.path if hasattr(context, "_shell") else "#00ffff"
        cmd_color = context._shell.config.colors.command if hasattr(context, "_shell") else "#ffffff"
        
        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText
        
        for idx, cmd in entries:
            # We use print_formatted_text for colored output if stdout is terminal-like
            # Otherwise fall back to plain _write
            if hasattr(stdout, "isatty") and stdout.isatty():
                print_formatted_text(FormattedText([
                    (path_color, f"{idx:3}  "),
                    (cmd_color, cmd)
                ]), file=stdout)
            else:
                self._write(f"{idx:3}  {cmd}\n", stdout)
