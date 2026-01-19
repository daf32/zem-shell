from collections import defaultdict
from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class HelpCommand(BaseCommand):
    name = "help"
    help = "Show help information"
    usage = "help [command]"

    def print_commands(self, commands, stdout):
        stdout.write("\nAvailable commands:\n")

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
            stdout.write(f"\n[{tag}]\n")
            for cmd in sorted(tags[tag], key=lambda cmd: cmd.name):
                usage_suffix = f" (usage: {cmd.usage})" if getattr(cmd, "usage", None) else ""
                stdout.write(
                    f"  {cmd.name:<{max_cmd_name_length}} - {cmd.help}{usage_suffix}\n"
                )

        if without_tags:
            stdout.write("\n[other]\n")
            
            for cmd in sorted(without_tags, key=lambda cmd: cmd.name):
                usage_suffix = f" (usage: {cmd.usage})" if getattr(cmd, "usage", None) else ""
                stdout.write(
                    f"  {cmd.name:<{max_cmd_name_length}} - {cmd.help}{usage_suffix}\n"
                )

        stdout.write("\nType: help <command>\n")


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
            stdout.write(f"help: command '{cmd_name}' not found\n")
            return

        if stdout:
            stdout.write(f"Command: {cmd.name}\n")
            stdout.write(f"Description: {cmd.help}\n")
            if cmd.usage:
                stdout.write(f"Usage: {cmd.usage}\n")
            if cmd.tags:
                stdout.write(f"Tags: {', '.join(cmd.tags)}\n")
            if getattr(cmd, "examples", None):
                stdout.write("Examples:\n")
                for ex in cmd.examples:
                    stdout.write(f"  {ex}\n")