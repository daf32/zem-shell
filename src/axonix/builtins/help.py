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
        stdout.write("Available commands:\n\n")
        for name in sorted(commands):
            cmd = commands[name]
            stdout.write(f"{name:10} - {cmd.help}\n")
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
            raise ArgumentError(self.name, cmd_name)

        if stdout:
            stdout.write(f"Command: {cmd.name}\n")
            stdout.write(f"Description: {cmd.help}\n")
            if cmd.usage:
                stdout.write(f"Usage: {cmd.usage}\n")
