from collections import defaultdict
from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class HelpCommand(BaseCommand):
    name = "help"
    help = "Show help information"
    usage = "help [command]"

    def print_commands(self, commands, stdout):
        self._write("\nAvailable commands:\n", stdout)

        tags = defaultdict(list)
        without_tags = []

        max_cmd_name_length = max(len(cmd.name) for cmd in commands.values())

        for cmd in commands.values():
            if cmd.tags:
                for tag in cmd.tags:
                    tags[tag].append(cmd)
            else:
                without_tags.append(cmd)

        for tag in sorted(tags):
            self._write(f"\n[{tag}]\n", stdout)
            for cmd in sorted(tags[tag], key=lambda cmd: cmd.name):
                usage_suffix = f" (usage: {cmd.usage})" if getattr(cmd, "usage", None) else ""
                self._write(
                    f"  {cmd.name:<{max_cmd_name_length}} - {cmd.help}{usage_suffix}\n", stdout
                )

        if without_tags:
            self._write("\n[other]\n", stdout)
            
            for cmd in sorted(without_tags, key=lambda cmd: cmd.name):
                usage_suffix = f" (usage: {cmd.usage})" if getattr(cmd, "usage", None) else ""
                self._write(
                    f"  {cmd.name:<{max_cmd_name_length}} - {cmd.help}{usage_suffix}\n", stdout
                )

        self._write("\nType: help <command>\n", stdout)


    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        commands = context.commands

        if not args:
            if stdout:
                self.print_commands(commands, stdout)
            return

        cmd_name = args[0]
        cmd = commands.get(cmd_name)

        if not cmd:
            self._write(f"help: command '{cmd_name}' not found\n", stdout)
            return

        self._write(f"Command: {cmd.name}\n", stdout)
        self._write(f"Description: {cmd.help}\n", stdout)
        if cmd.usage:
            self._write(f"Usage: {cmd.usage}\n", stdout)
        if cmd.tags:
            self._write(f"Tags: {', '.join(cmd.tags)}\n", stdout)
        if getattr(cmd, "examples", None):
            self._write("Examples:\n", stdout)
            for ex in getattr(cmd, "examples", []):
                self._write(f"  {ex}\n", stdout)