from axonix.core.context import ExecutionContext
from axonix.core.parser import Parser
from axonix.core.executor import CommandExecutor

from axonix.builtins import load_plugins
from axonix.builtins.base import BaseCommand
from axonix.builtins.registry import CommandRegistry

from axonix.config.settings import AppConfig

from axonix.errors.base_error import CLIError

from typing import Dict, Optional
import os
import signal
import sys
import threading
import subprocess

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from axonix.ui.lexer import AxonixLexer
from axonix.ui.completer import AxonixCompleter
from axonix.utils.git import get_git_info, format_git_branch
from axonix.utils.venv import activate_venv, get_venv_info


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
        self.history_file = self.config.history.file
        self.rc_file = self.config.rc.file

        if commands is None:
            load_plugins()
            self.commands = CommandRegistry.get_all_commands()
        else:
            self.commands = commands

        self.context.commands = self.commands
        self.executor = CommandExecutor(self.context)
        
        self.context._shell = self
        self._setup_prompt_session()
        self._setup_signal_handlers()
        
        if self.config.rc.auto_create and not os.path.exists(self.rc_file):
            self._create_default_rc()

        self._load_rc_file()

        if self.config.venv.auto:
            activate_venv(self.context)
            
        self._sync_plugin_configs()

    def _sync_plugin_configs(self):
        """Sync default plugin configurations to the config file."""
        from axonix.config.settings import CONFIG_PATH
        import json
        
        updated = False
        plugins_config = self.config.plugins.copy()
        
        for name, cmd in self.commands.items():
            defaults = cmd.get_default_config()
            if defaults and name not in plugins_config:
                plugins_config[name] = defaults
                updated = True
        
        if updated:
            try:
                # We update the file directly to persist changes
                if os.path.exists(CONFIG_PATH):
                    with open(CONFIG_PATH, 'r') as f:
                        data = json.load(f)
                else:
                    data = {}
                
                # Ensure plugins section exists
                if "plugins" not in data:
                    data["plugins"] = {}
                
                # Update with new defaults (only if not present)
                for k, v in plugins_config.items():
                    if k not in data["plugins"]:
                        data["plugins"][k] = v
                
                with open(CONFIG_PATH, 'w') as f:
                    json.dump(data, f, indent=4)
                
                # Update in-memory config
                self.config.plugins = plugins_config
                
            except Exception as e:
                print(f"Warning: Failed to sync plugin configs: {e}")

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
        
        # Build style from config colors
        c = self.config.colors
        self.style = Style.from_dict({
            'command': f'bold {c.command}',
            'variable': c.variable,
            'operator': c.operator,
            'comment': c.comment,
            'string': c.string,
            'path': c.path,
            'prompt_symbol': f'bold {c.prompt_symbol}',
            'exit_code_ok': c.exit_code_ok,
            'exit_code_err': c.exit_code_err,
            'git_branch': c.info,  # Use info color for git branch
            'venv': c.info,  # Use info color for venv
            'error': c.error,
        })
        
        self.session = PromptSession(
            history=history,
            lexer=AxonixLexer(self),
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

    def _format_path(self, current_dir: str) -> str:
        """Format current directory for display."""
        home = os.path.expanduser("~")
        if current_dir.startswith(home):
            display_path = current_dir.replace(home, "~")
        else:
            display_path = current_dir

        if self.config.input.show_full_path:
            return display_path

        parts = display_path.strip("/").split("/")
        depth = self.config.input.path_depth
        if len(parts) > depth:
            return "/".join(parts[-depth:])
        return display_path

    def _format_path_display(self, path: str) -> str:
        """Add ~ prefix if path doesn't start with it."""
        return path if path.startswith("~") else f"~ {path}"

    def _build_colored_prompt(self, venv_info: str | None, path: str, git_info: str, exit_code: int) -> list:
        """Build colored prompt components."""
        code_class = 'exit_code_ok' if exit_code == 0 else 'exit_code_err'
        path_display = self._format_path_display(path)
        
        prompt_parts = []

        if venv_info:
            prompt_parts.append(('class:venv', f'[{venv_info}] '))

        if self.config.input.show_exit_code:
            prompt_parts.append((f'class:{code_class}', f'{exit_code} '))
        
        prompt_parts.append(('class:path', path_display))
        
        if git_info:
            prompt_parts.append(('class:git_branch', git_info))
        
        prompt_parts.extend([
            ('', ' '),
            ('class:prompt_symbol', self.config.input.prompt),
            ('', ' ')
        ])
        return prompt_parts

    def _build_text_prompt(self, venv_info: str | None, path: str, git_info: str, exit_code: int) -> str:
        """Build text-only prompt."""
        prompt_text = f"{exit_code} " if self.config.input.show_exit_code else ""
        path_display = self._format_path_display(path)
        prompt_text += f"{venv_info}{path_display}{git_info} {self.config.input.prompt} "
        return prompt_text

    def _get_input(self):
        real_cwd = os.getcwd()
        display_path = self._format_path(real_cwd)
        exit_code = self.context.last_exit_code
        
        git_display = ""
        if getattr(self.config.input, "show_git_info", False):
            git_info = get_git_info(real_cwd)
            if git_info:
                branch, status = git_info
                git_display = f" ({format_git_branch(branch, status)})"

        venv_display = get_venv_info() if getattr(self.config.input, "show_venv_info", False) else None

        if self.config.input.color_prompt:
            prompt_html = self._build_colored_prompt(venv_display, display_path, git_display, exit_code)
        else:
            prompt_html = self._build_text_prompt(venv_display, display_path, git_display, exit_code)

        return self.session.prompt(prompt_html)

    def _print_error(self, message: str):
        from prompt_toolkit import print_formatted_text, HTML
        from axonix.utils.colors import error_tag
        print_formatted_text(HTML(f'{error_tag(self.config)} {message}'), file=sys.stderr)

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
            units = Parser(
                user_input,
                self.context.variables,
                self.context.aliases,
                self.config
            ).parse()

            last_exit_code = 0
            for unit in units:
                pipeline = unit["pipeline"]
                logic = unit["logic"]

                # Execute the pipeline
                last_exit_code = self._execute_pipeline(pipeline)
                self.context.last_exit_code = last_exit_code

                # Logic control
                if logic == "&&" and last_exit_code != 0:
                    break
                if logic == "||" and last_exit_code == 0:
                    break
                # Semicolon (;) continues regardless of exit code

            # Sync variables back to environment after execution
            self.context.sync_to_environment()

        except CLIError as e:
            self.context.last_exit_code = getattr(e, "exit_code", 1)
            self._print_error(str(e))
        except Exception as e:
            self.context.last_exit_code = 1
            self._print_error(f"internal error: {e}")

    def _execute_pipeline(self, pipeline: list[dict]) -> int:
        """Execute a single pipeline and return the exit code of the last command."""
        processes = []
        pipe_fds = []
        prev_pipe_read = None
        exit_code = 0

        def safe_close(fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

        try:
            for i, cmd_info in enumerate(pipeline):
                cmd_name = cmd_info["name"]
                args = cmd_info["args"]
                stdin_file = cmd_info["stdin_file"]
                stdout_file = cmd_info["stdout_file"]
                append = cmd_info.get("append", False)
                background = cmd_info.get("background", False)

                is_last = i == len(pipeline) - 1
                
                # Background processes can't be part of a pipeline
                if background and len(pipeline) > 1:
                    self._print_error("background processes cannot be used in pipelines")
                    return 1

                # Initialize stdin from previous pipe or input redirection
                current_stdin = prev_pipe_read
                if i == 0:
                    current_stdin = None

                # Handle input redirection (takes precedence over pipe)
                if stdin_file:
                    try:
                        fd_in = os.open(stdin_file, os.O_RDONLY)
                        # Close previous stdin if it was from a pipe
                        if current_stdin is not None:
                            safe_close(current_stdin)
                        current_stdin = fd_in
                    except FileNotFoundError:
                        self._print_error(f"no such file or directory: {stdin_file}")
                        # Clean up before returning
                        for fd in pipe_fds:
                            safe_close(fd)
                        return 1
                    except OSError as e:
                        self._print_error(f"cannot open file {stdin_file}: {e}")
                        for fd in pipe_fds:
                            safe_close(fd)
                        return 1

                # Initialize stdout - will be pipe or output redirection
                current_stdout = None
                pipe_read = None
                pipe_write = None

                # Create pipe for next command if not last
                if not is_last:
                    pipe_read, pipe_write = os.pipe()
                    pipe_fds.extend([pipe_read, pipe_write])
                    current_stdout = pipe_write
                
                # Handle output redirection (takes precedence over pipe)
                # For background processes, redirect to /dev/null if no file specified
                if background and not stdout_file:
                    stdout_file = os.devnull
                    append = False
                
                if stdout_file:
                    try:
                        flags = os.O_WRONLY | os.O_CREAT
                        if append:
                            flags |= os.O_APPEND
                        else:
                            flags |= os.O_TRUNC
                        
                        fd_out = os.open(stdout_file, flags, 0o644)
                        # Close pipe write end if we're redirecting to file
                        if current_stdout is not None:
                            safe_close(current_stdout)
                            # Also close pipe_read since we won't use it
                            if pipe_read is not None:
                                safe_close(pipe_read)
                                pipe_read = None
                        current_stdout = fd_out
                    except OSError as e:
                        self._print_error(f"cannot open file {stdout_file}: {e}")
                        # Clean up before returning
                        for fd in pipe_fds:
                            safe_close(fd)
                        return 1
                
                # For background processes, redirect stdin from /dev/null if not specified
                if background and not stdin_file and current_stdin is None:
                    try:
                        current_stdin = os.open(os.devnull, os.O_RDONLY)
                    except OSError:
                        pass

                command = self.commands.get(cmd_name)

                if command:
                    # Execute builtin command
                    stdin_fd = os.dup(current_stdin) if current_stdin is not None else None
                    stdout_fd = os.dup(current_stdout) if current_stdout is not None else None
                    
                    thread = self.executor.execute_builtin(
                        command, args, stdin_fd, stdout_fd
                    )
                    processes.append(thread)

                    safe_close(current_stdout)
                    safe_close(current_stdin)
                else:
                    # Execute external command
                    try:
                        process = self.executor.execute_external(
                            cmd_name, args, current_stdin, current_stdout
                        )
                        processes.append(process)

                        safe_close(current_stdout)
                        safe_close(current_stdin)
                    except FileNotFoundError:
                        self._print_error(f"command not found: {cmd_name}")
                        # Clean up before returning
                        for fd in pipe_fds:
                            safe_close(fd)
                        return 127
                    except Exception as e:
                        self._print_error(f"failed to execute {cmd_name}: {e}")
                        # Clean up before returning
                        for fd in pipe_fds:
                            safe_close(fd)
                        return 1

                # Only set prev_pipe_read if we actually have a pipe (not redirected to file)
                if pipe_read is not None:
                    prev_pipe_read = pipe_read
                else:
                    # If we redirected output to file, there's no pipe for next command
                    prev_pipe_read = None

            # Handle background processes
            if background and processes:
                bg_process = processes[-1]  # Last process is the background one
                bg_info = {
                    "pid": None,
                    "cmd": f"{cmd_name} {' '.join(args)}",
                    "process": bg_process
                }
                
                if isinstance(bg_process, subprocess.Popen):
                    bg_info["pid"] = bg_process.pid
                    # Don't wait for background process
                    self.context._background_processes.append(bg_info)
                    print(f"[{bg_info['pid']}] {bg_info['cmd']}")
                    return 0  # Background processes return success immediately
                else:
                    # Builtin commands can't really run in background properly
                    # but we'll start them and not wait
                    self.context._background_processes.append(bg_info)
                    print(f"[background] {bg_info['cmd']}")
                    return 0
            
            # Wait for all processes in the pipeline
            for idx, p in enumerate(processes):
                is_last_process = idx == len(processes) - 1
                if isinstance(p, threading.Thread):
                    p.join()
                    # Only use exit code from last builtin command in pipeline
                    if is_last_process:
                        exit_code = self.context.last_exit_code
                else:
                    exit_code = p.wait()
                    # Update context for consistency
                    if is_last_process:
                        self.context.last_exit_code = exit_code

            return exit_code

        except Exception as e:
            self._print_error(f"Pipeline error: {e}")
            return 1
        finally:
            # Clear finished processes from executor's memory
            self.executor.clear_finished()
            
            # Ensure all pipeline-internal FDs are closed
            for fd in pipe_fds:
                safe_close(fd)
            
            # Clean up prev_pipe_read if it was left open
            if prev_pipe_read is not None:
                safe_close(prev_pipe_read)

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
