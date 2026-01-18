from axonix.core.context import ExecutionContext
from axonix.core.parser import Parser

from axonix.builtins import load_plugins
from axonix.builtins.base import BaseCommand

from axonix.config.settings import config

from axonix.errors.base_error import CLIError

from typing import Dict, Optional
import readline
import os
import subprocess
import sys
import threading


class Shell:
    HISTORY_FILE = os.path.expanduser("~/.axonix_history")

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
        if os.path.exists(self.HISTORY_FILE):
            try:
                readline.read_history_file(self.HISTORY_FILE)
            except Exception as e:
                # libedit on macOS can be touchy about history formats
                pass

        if "libedit" in readline.__doc__:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
        
        readline.set_completer(self.complete)
        readline.set_completer_delims(" \t\n;")

    def complete(self, text, state):
        begidx = readline.get_begidx()
        
        # commands autocomplete
        if begidx == 0:
            options = [cmd for cmd in self.commands.keys() if cmd.startswith(text)]
            if state < len(options):
                return options[state]
            return None

        # paths autocomplete
        try:
            line = readline.get_line_buffer()
            cmd_name = line.split()[0] if line.strip() else ""
            
            dirname = os.path.dirname(text)
            filename = os.path.basename(text)
            
            search_dir = dirname if dirname else "."
            if not os.path.isdir(search_dir):
                return None

            files = os.listdir(search_dir)
            
            # filter files by name
            options = [os.path.join(dirname, f) for f in files if f.startswith(filename)]
            
            formatted_options = []
            for opt in options:
                is_dir = os.path.isdir(opt)
                
                # if command is 'cd', offer only directories
                if cmd_name == "cd" and not is_dir:
                    continue
                    
                if is_dir:
                    formatted_options.append(opt + "/")
                else:
                    formatted_options.append(opt)

            if state < len(formatted_options):
                return formatted_options[state]
        except Exception:
            pass
            
        return None

    def _save_history(self):
        try:
            readline.write_history_file(self.HISTORY_FILE)
        except Exception as e:
            # On some systems/versions, libedit may fail with EPERM or other errors
            pass

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

    def _get_input(self, message=""):
        cwd = os.getcwd()
        home = os.path.expanduser("~")

        if cwd.startswith(home):
            cwd = cwd.replace(home, "~")

        if config.settings.input.show_full_path:
            display_path = cwd
        else:
            parts = cwd.strip("/").split("/")
            depth = config.settings.input.path_depth
            if len(parts) > depth:
                display_path = "/".join(parts[-depth:])
            else:
                display_path = cwd

        if display_path.startswith("~"):
            prompt = f"{display_path} {config.settings.input.prompt} {message}"
        else:
            prompt = f"~ {display_path} {config.settings.input.prompt} {message}"
        return input(prompt)

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
                    user_input = self._get_input()
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
