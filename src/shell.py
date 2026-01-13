from src.context import ExecutionContext
from src.parser import Parser

from src.commands import load_plugins
from src.commands.base import BaseCommand

from src.symbols import Operators

from src.errors.base import CLIError
from src.errors.input import UnknownCommandError

from typing import Dict, Optional
import readline
import os

class Shell:
    HISTORY_FILE = os.path.expanduser("~/.cli_shell_history")

    def _setup_readline(self):
        try:
            if os.path.exists(self.HISTORY_FILE):
                readline.read_history_file(self.HISTORY_FILE)
        except FileNotFoundError:
            pass

        readline.set_completer(self.complete)
        readline.parse_and_bind("tab: complete")

    def complete(self, text, state):
        options = [cmd for cmd in self.commands.keys() if cmd.startswith(text)]
        if state < len(options):
            return options[state]
        return None

    def _save_history(self):
        try:
            readline.write_history_file(self.HISTORY_FILE)
        except IOError as e:
            print(f"Error saving history: {e}")
    def __init__(self, commands: Optional[Dict[str, BaseCommand]] = None):
        self.context = ExecutionContext()
        
        if commands is None:
            load_plugins()
            self.commands = self._collect_commands()
        else:
            self.commands = commands
            
        self.context.commands = self.commands
        
        self._setup_readline()

    def _collect_commands(self) -> Dict[str, BaseCommand]:
        commands = {}
        for cmd_class in BaseCommand.__subclasses__():
            cmd = cmd_class()
            commands[cmd.name] = cmd
        return commands
    
    def _close_shell(self):
        self._save_history()
        self.context.running = False
        print("\nClosing shell...")
    
    def input(self, message=""):
        return input(f"{Operators.input.value} {message}")
    
    def run(self):
        while self.context.running:
            try:

                try:
                    user_input = self.input()
                except (KeyboardInterrupt, EOFError):
                    self._close_shell()
                    return
                
                if not user_input.strip():
                    continue

                self.context.history.append(user_input)

                command_name, args = Parser(user_input, self.context.variables).parse()

                command = self.commands.get(command_name)

                if not command:
                    raise UnknownCommandError(command_name)

                command.execute(args, self.context)

            except CLIError as e:
                print(e)

            except Exception as e:
                print(f"Internal error: {e}")
        
        self._save_history()