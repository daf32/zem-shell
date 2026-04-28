from collections import defaultdict
from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class HelpCommand(BaseCommand):
    name = "help"
    help = "Show help information for commands"
    usage = "help [command]"
    tags = ["builtin"]
    examples = [
        "help           - List all commands",
        "help cd        - Show help for 'cd' command",
        "help theme     - Show help for 'theme' command",
    ]

    def print_commands(self, commands, context, stdout):
        """Print list of all available commands grouped by tag."""
        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText
        
        # Get colors from config
        colors = None
        if hasattr(context, "_shell") and context._shell:
            colors = context._shell.config.colors
        
        self._write("\nAvailable commands:\n", stdout)

        tags = defaultdict(list)
        without_tags = []

        # Handle empty commands dict
        if not commands:
            self._write("  No commands available\n", stdout)
            return

        max_cmd_name_length = max(len(cmd.name) for cmd in commands.values())

        for cmd in commands.values():
            if cmd.tags:
                for tag in cmd.tags:
                    tags[tag].append(cmd)
            else:
                without_tags.append(cmd)

        for tag in sorted(tags):
            if colors:
                print_formatted_text(FormattedText([
                    (colors.info, f"\n[{tag}]")
                ]))
            else:
                self._write(f"\n[{tag}]\n", stdout)
            
            for cmd in sorted(tags[tag], key=lambda c: c.name):
                desc = cmd.help or "No description"
                if colors:
                    print_formatted_text(FormattedText([
                        (colors.command, f"  {cmd.name:<{max_cmd_name_length}}"),
                        ("", f" - {desc}")
                    ]))
                else:
                    self._write(f"  {cmd.name:<{max_cmd_name_length}} - {desc}\n", stdout)

        if without_tags:
            if colors:
                print_formatted_text(FormattedText([
                    (colors.info, "\n[other]")
                ]))
            else:
                self._write("\n[other]\n", stdout)
            
            for cmd in sorted(without_tags, key=lambda c: c.name):
                desc = cmd.help or "No description"
                if colors:
                    print_formatted_text(FormattedText([
                        (colors.command, f"  {cmd.name:<{max_cmd_name_length}}"),
                        ("", f" - {desc}")
                    ]))
                else:
                    self._write(f"  {cmd.name:<{max_cmd_name_length}} - {desc}\n", stdout)

        self._write("\nType 'help <command>' for detailed information.\n", stdout)

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        commands = context.commands

        if not args:
            self.print_commands(commands, context, stdout)
            return

        cmd_name = args[0]
        cmd = commands.get(cmd_name)

        if not cmd:
            # Check if it's an alias
            if cmd_name in context.aliases:
                alias_value = context.aliases[cmd_name]
                self._write(f"'{cmd_name}' is an alias for: {alias_value}\n", stdout)
                return
            
            self._write(f"help: command '{cmd_name}' not found\n", stdout)
            return 1

        # Detailed command info
        self._write(f"\nCommand: {cmd.name}\n", stdout)
        self._write(f"Description: {cmd.help or 'No description'}\n", stdout)
        
        if cmd.usage:
            self._write(f"Usage: {cmd.usage}\n", stdout)
        
        if cmd.tags:
            self._write(f"Tags: {', '.join(cmd.tags)}\n", stdout)
        
        examples = getattr(cmd, "examples", None)
        if examples:
            self._write("\nExamples:\n", stdout)
            for ex in examples:
                self._write(f"  {ex}\n", stdout)
        
        self._write("", stdout)  # Empty line at the end