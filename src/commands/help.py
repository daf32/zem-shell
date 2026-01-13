from typing import TYPE_CHECKING
from src.commands.base import BaseCommand
from src.errors.input import ArgumentError

if TYPE_CHECKING:
    from src.context import ExecutionContext

class HelpCommand(BaseCommand):
    name = "help"
    help = "Show help information"
    usage = "help [command]"

    def print_commands(self, commands):
        print("Avalible commands:\n")
        for name in sorted(commands):
            cmd = commands[name]
            print(f"{name:10} - {cmd.help}")
        print("\nType: help <command>")

    def execute(self, args: list[str], context: 'ExecutionContext'):
        commands = context.commands

        if not args:
            self.print_commands(commands)
            return 
        
        cmd_name = args[0]
        cmd = commands.get(cmd_name)

        if not cmd:
            raise ArgumentError(self.name, cmd_name)
        
        print(f"Command: {cmd.name}")
        print(f"Description: {cmd.help}")
        if cmd.usage:
            print(f"Usage: {cmd.usage}")