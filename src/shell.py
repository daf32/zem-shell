from src.context import ExecutionContext
from src.parser import Parser

from src.commands import load_plugins
from src.commands.base import BaseCommand

from src.symbols import Operators

from src.errors.base_error import CLIError

from typing import Dict, Optional
import readline
import os
import subprocess
import sys
import threading


class Shell:
    HISTORY_FILE = os.path.expanduser("~/.cli_shell_history")

    def __init__(self, commands: Optional[Dict[str, BaseCommand]] = None):
        self.context = ExecutionContext()

        if commands is None:
            load_plugins()
            self.commands = self._collect_commands()
        else:
            self.commands = commands

        self.context.commands = self.commands

        self._setup_readline()

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

    def _run_internal_command(self, command, args, stdin_fd, stdout_fd):
        """Helper to run internal command in a thread"""
        stdin = sys.stdin
        stdout = sys.stdout

        if stdin_fd is not None:
            stdin = os.fdopen(stdin_fd, "r")

        if stdout_fd is not None:
            stdout = os.fdopen(stdout_fd, "w")

        try:
            command.execute(args, self.context, stdin=stdin, stdout=stdout)
        except BrokenPipeError:
            pass
        except Exception as e:
            sys.stderr.write(f"Error in {command.name}: {e}\n")
        finally:
            if stdin is not sys.stdin:
                try:
                    stdin.close()
                except OSError:
                    pass
            if stdout is not sys.stdout:
                try:
                    stdout.close()
                except OSError:
                    pass

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

                pipeline = Parser(user_input, self.context.variables).parse()

                processes = []
                prev_pipe_read = None

                for i, (cmd_name, args) in enumerate(pipeline):
                    is_last = i == len(pipeline) - 1

                    current_stdin = prev_pipe_read
                    if i == 0:
                        current_stdin = None

                    current_stdout = None
                    pipe_write = None
                    pipe_read = None

                    if not is_last:
                        pipe_read, pipe_write = os.pipe()
                        current_stdout = pipe_write
                    else:
                        current_stdout = None

                    command = self.commands.get(cmd_name)

                    if command:
                        t_stdin = (
                            os.dup(current_stdin) if current_stdin is not None else None
                        )
                        t_stdout = (
                            os.dup(current_stdout)
                            if current_stdout is not None
                            else None
                        )

                        t = threading.Thread(
                            target=self._run_internal_command,
                            args=(command, args, t_stdin, t_stdout),
                        )
                        t.start()
                        processes.append(t)

                        if current_stdout is not None:
                            os.close(current_stdout)
                        if current_stdin is not None:
                            os.close(current_stdin)

                    else:
                        try:
                            p = subprocess.Popen(
                                [cmd_name] + args,
                                stdin=current_stdin,
                                stdout=current_stdout,
                            )
                            processes.append(p)

                            if current_stdout is not None:
                                os.close(current_stdout)
                            if current_stdin is not None:
                                os.close(current_stdin)

                        except FileNotFoundError:
                            print(f"Command not found: {cmd_name}")
                            if current_stdout is not None:
                                os.close(current_stdout)
                            if pipe_read is not None:
                                os.close(pipe_read)
                            if current_stdin is not None:
                                os.close(current_stdin)
                            break

                    prev_pipe_read = pipe_read

                for p in processes:
                    if isinstance(p, threading.Thread):
                        p.join()
                    else:
                        p.wait()

            except CLIError as e:
                print(e)

            except Exception as e:
                print(f"Internal error: {e}")

        self._save_history()
