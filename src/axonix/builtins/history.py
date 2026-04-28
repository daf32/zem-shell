from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class HistoryCommand(BaseCommand):
    help = "Show command history"
    usage = "history [-c|--clear] [limit] [search_term]"
    tags = ["builtin"]
    examples = [
        "history          - Show all history",
        "history 10       - Show last 10 commands",
        "history git      - Show commands containing 'git'",
        "history -c       - Clear history",
    ]

    def clear(self, context: "ExecutionContext"):
        """Clear command history."""
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
            elif arg.startswith("-"):
                # Skip unknown flags
                continue
            else:
                search_term = arg

        history = context.history
        
        # Filter by search term
        if search_term:
            entries = [
                (i + 1, cmd) for i, cmd in enumerate(history)
                if search_term.lower() in cmd.lower()
            ]
        else:
            entries = [(i + 1, cmd) for i, cmd in enumerate(history)]

        # Apply limit (last N)
        if limit and limit < len(entries):
            entries = entries[-limit:]

        if not entries:
            if search_term:
                self._write(f"No history entries matching '{search_term}'\n", stdout)
            else:
                self._write("No history entries\n", stdout)
            return

        # Get colors for formatting if available
        path_color = "#00ffff"
        cmd_color = "#ffffff"
        if hasattr(context, "_shell") and context._shell:
            path_color = context._shell.config.colors.path
            cmd_color = context._shell.config.colors.command
        
        # Check if we can use colored output (stdout is a real terminal)
        use_colors = stdout is None or (hasattr(stdout, "isatty") and stdout.isatty())
        
        if use_colors:
            from prompt_toolkit import print_formatted_text
            from prompt_toolkit.formatted_text import FormattedText
            
            for idx, cmd in entries:
                print_formatted_text(FormattedText([
                    (path_color, f"{idx:5}  "),
                    (cmd_color, cmd)
                ]))
        else:
            # Plain text output for pipes/redirects
            for idx, cmd in entries:
                self._write(f"{idx:5}  {cmd}\n", stdout)
