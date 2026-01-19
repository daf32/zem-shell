from axonix.core.context import ExecutionContext
from axonix.core.parser import Parser
from axonix.core.executor import CommandExecutor

from axonix.builtins import load_plugins
from axonix.builtins.base import BaseCommand
from axonix.builtins.registry import CommandRegistry

from axonix.config.settings import AppConfig

from axonix.errors.base_error import CLIError

from typing import Dict, Optional, List, Tuple
import os
import signal
import sys
import threading

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML

from axonix.ui.lexer import AxonixLexer
from axonix.ui.completer import AxonixCompleter


class Shell:
    HISTORY_FILE = os.path.expanduser("~/.axonix_history")
    RC_FILE = os.path.expanduser("~/.axonixrc")
    
    def __init__(
        self, 
        commands: Optional[Dict[str, BaseCommand]] = None,
        config: Optional[AppConfig] = None
    ):
        self.config = config or AppConfig()
        self.context = ExecutionContext()
        # Respect configurable paths
        self.history_file = self.config.history.file
        self.rc_file = self.config.rc.file

        if commands is None:
            load_plugins()
            self.commands = CommandRegistry.get_all_commands()
        else:
            self.commands = commands

        self.context.commands = self.commands
        self.executor = CommandExecutor(self.context)
        self._setup_prompt_session()
        self._setup_signal_handlers()
        
        if self.config.rc.auto_create and not os.path.exists(self.rc_file):
            self._create_default_rc()
            
        self._load_rc_file()

    def _create_default_rc(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(current_dir, "..", "resources", "axonixrc.default")
        
        try:
            if os.path.isfile(template_path):
                import shutil
                shutil.copy(template_path, self.rc_file)
            else:
                with open(self.rc_file, "w", encoding="utf-8") as f:
                    f.write("# Axonix Shell (Minimal Config)\n")
                    f.write("set SHELL axonix\n")
                    f.write("alias help='help'\n")
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to create default {self.rc_file}: {e}\n")

    def _load_rc_file(self):
        if os.path.exists(self.rc_file):
            try:
                with open(self.rc_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        self._execute_line(line, add_to_history=False)
            except Exception as e:
                print(f"Error loading {self.rc_file}: {e}")

    def _setup_prompt_session(self):
        """Setup prompt_toolkit session with history, lexer and completer."""
        history = FileHistory(self.history_file) if self.config.history.enable else None
        
        self.style = Style.from_dict({
            'command': '#ffb86c bold',
            'variable': '#f1fa8c',
            'operator': '#50fa7b',
            'comment': '#6272a4',
            'string': '#ff79c6',
            'path': '#8be9fd',
            'prompt_symbol': '#ffffff bold',
            'exit_code_ok': '#50fa7b',
            'exit_code_err': '#ff5555',
        })
        
        self.session = PromptSession(
            history=history,
            lexer=AxonixLexer(self.config),
            completer=AxonixCompleter(self),
            style=self.style,
            complete_while_typing=True
        )

    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            """Handle SIGINT (Ctrl+C) and SIGTERM."""
            print("\nInterrupted")
            self.executor.cleanup_processes()
            self._close_shell()
            sys.exit(130 if signum == signal.SIGINT else 0)
        
        signal.signal(signal.SIGINT, signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)



    def _close_shell(self):
        """Close shell gracefully."""
        self.executor.cleanup_processes()
        self.context.sync_to_environment()
        self.context.running = False
        print("Closing shell...")

    def _get_input(self, message=""):
        cwd = os.getcwd()
        home = os.path.expanduser("~")

        if cwd.startswith(home):
            cwd = cwd.replace(home, "~")

        if self.config.input.show_full_path:
            display_path = cwd
        else:
            parts = cwd.strip("/").split("/")
            depth = self.config.input.path_depth
            if len(parts) > depth:
                display_path = "/".join(parts[-depth:])
            else:
                display_path = cwd

        exit_code = self.context.last_exit_code
        show_code = self.config.input.show_exit_code
        prompt_symbol = self.config.input.prompt

        # Build formatted prompt
        if self.config.input.color_prompt:
            code_class = 'exit_code_ok' if exit_code == 0 else 'exit_code_err'
            prompt_html = [
                (f'class:{code_class}', f'{exit_code} '),
                ('class:path', f'{display_path if display_path.startswith("~") else f"~ {display_path}"}'),
                ('', ' '),
                ('class:prompt_symbol', f'{prompt_symbol}'),
                ('', ' ')
            ]
        else:
            prompt_text = f"{exit_code} " if show_code else ""
            prompt_text += f"{display_path if display_path.startswith('~') else f'~ {display_path}'} {prompt_symbol} "
            prompt_html = prompt_text

        return self.session.prompt(prompt_html)

    def _print_error(self, message: str):
        sys.stderr.write(f"[error] {message}\n")

    def _add_history(self, entry: str):
        """Add entry to in-memory history respecting limits and settings."""
        history_cfg = self.config.history
        if not history_cfg.enable:
            return
        self.context.history.append(entry)
        if len(self.context.history) > history_cfg.max_entries:
            # keep only last max_entries
            self.context.history = self.context.history[-history_cfg.max_entries:]

    def _execute_line(self, user_input: str, add_to_history: bool = True):
        """Execute a command line with proper resource management."""
        if not user_input.strip():
            return

        if add_to_history:
            self._add_history(user_input)

        # Sync environment variables before execution
        self.context.sync_from_environment()

        try:
            pipeline = Parser(
                user_input,
                self.context.variables,
                self.context.aliases,
                self.config
            ).parse()

            processes = []
            pipe_fds = []  # Track all pipe FDs for cleanup
            prev_pipe_read = None

            exit_code = 0
            try:
                for i, cmd_info in enumerate(pipeline):
                    cmd_name = cmd_info["name"]
                    args = cmd_info["args"]
                    stdin_file = cmd_info["stdin_file"]
                    stdout_file = cmd_info["stdout_file"]
                    append = cmd_info.get("append", False)

                    is_last = i == len(pipeline) - 1

                    current_stdin = prev_pipe_read
                    if i == 0:
                        current_stdin = None

                    # Handle input redirection
                    if stdin_file:
                        try:
                            fd_in = os.open(stdin_file, os.O_RDONLY)
                            if current_stdin is not None:
                                os.close(current_stdin)
                            current_stdin = fd_in
                        except FileNotFoundError:
                            self._print_error(f"no such file or directory: {stdin_file}")
                            exit_code = 1
                            break

                    current_stdout = None
                    pipe_write = None
                    pipe_read = None

                    if not is_last:
                        pipe_read, pipe_write = os.pipe()
                        pipe_fds.extend([pipe_read, pipe_write])
                        current_stdout = pipe_write
                    
                    # Handle output redirection
                    if stdout_file:
                        try:
                            flags = os.O_WRONLY | os.O_CREAT
                            if append:
                                flags |= os.O_APPEND
                            else:
                                flags |= os.O_TRUNC
                            
                            fd_out = os.open(stdout_file, flags, 0o644)
                            if current_stdout is not None:
                                os.close(current_stdout)
                            current_stdout = fd_out
                        except OSError as e:
                            self._print_error(f"cannot open file {stdout_file}: {e}")
                            exit_code = 1
                            break

                    command = self.commands.get(cmd_name)

                    if command:
                        # Execute builtin command
                        # We pass duplicates because managed_fd will close them
                        stdin_fd = os.dup(current_stdin) if current_stdin is not None else None
                        stdout_fd = os.dup(current_stdout) if current_stdout is not None else None
                        
                        thread = self.executor.execute_builtin(
                            command, args, stdin_fd, stdout_fd
                        )
                        processes.append(thread)

                        # Close original FDs
                        if current_stdout is not None:
                            os.close(current_stdout)
                        if current_stdin is not None:
                            os.close(current_stdin)

                    else:
                        # Execute external command
                        try:
                            process = self.executor.execute_external(
                                cmd_name, args, current_stdin, current_stdout
                            )
                            processes.append(process)

                            # Close FDs (subprocess owns them now)
                            if current_stdout is not None:
                                os.close(current_stdout)
                            if current_stdin is not None:
                                os.close(current_stdin)

                        except FileNotFoundError:
                            self._print_error(f"command not found: {cmd_name}")
                            exit_code = 127
                            if current_stdout is not None: os.close(current_stdout)
                            if pipe_read is not None: os.close(pipe_read)
                            if current_stdin is not None: os.close(current_stdin)
                            break
                        except ValueError as e:
                            self._print_error(f"invalid command: {e}")
                            exit_code = 1
                            if current_stdout is not None: os.close(current_stdout)
                            if pipe_read is not None: os.close(pipe_read)
                            if current_stdin is not None: os.close(current_stdin)
                            break

                    prev_pipe_read = pipe_read

                # Wait for all processes to complete
                for p in processes:
                    if isinstance(p, threading.Thread):
                        p.join()
                    else:
                        exit_code = p.wait()
                        if exit_code != 0 and p.stderr:
                            stderr_output = p.stderr.read().decode('utf-8', errors='ignore')
                            if stderr_output:
                                self._print_error(stderr_output.strip())

            finally:
                # Ensure all pipe FDs are closed
                for fd in pipe_fds:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

            # Sync variables back to environment after execution
            self.context.sync_to_environment()
            self.context.last_exit_code = exit_code

        except CLIError as e:
            self.context.last_exit_code = getattr(e, "exit_code", 1)
            self._print_error(str(e))
        except Exception as e:
            self.context.last_exit_code = 1
            self._print_error(f"internal error: {e}")

    def run(self):
        while self.context.running:
            try:
                try:
                    user_input = self._get_input()
                except (KeyboardInterrupt, EOFError):
                    self._close_shell()
                    return

                self._execute_line(user_input)

            except Exception as e:
                print(f"Internal error: {e}")
