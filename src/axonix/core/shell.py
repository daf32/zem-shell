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
import time
from datetime import datetime
import termios

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
        self._last_command_duration: Optional[float] = None  # Duration in seconds
        self._setup_prompt_session()
        self._setup_signal_handlers()
        self._interrupted = False
        
        if self.config.rc.auto_create and not os.path.exists(self.rc_file):
            self._create_default_rc()

        self._load_rc_file()

        if self.config.venv.auto:
            activate_venv(self.context)
            
        self._sync_plugin_configs()

        self._shell_pgid = os.getpgrp()
        self._tty_fd = sys.stdin.fileno()

        self._orig_term_attrs = termios.tcgetattr(self._tty_fd)

        new_attrs = termios.tcgetattr(self._tty_fd)
        new_attrs[3] = new_attrs[3] & ~termios.ECHOCTL
        termios.tcsetattr(self._tty_fd, termios.TCSANOW, new_attrs)

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

    def _clear_current_line(self):
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def _build_style(self) -> Style:
        """Build prompt_toolkit style from config colors."""
        c = self.config.colors
        return Style.from_dict({
            # Commands and syntax
            'command': f'bold {c.command}',
            'variable': c.variable,
            'operator': c.operator,
            'comment': f'italic {c.comment}',
            'string': c.string,
            
            # Paths and files
            'path': c.path,
            'path-notfound': f'underline {c.error}',  # Non-existent paths
            
            # Arguments
            'flag': c.operator,  # Command flags like -v, --help
            'number': c.variable,  # Numeric values
            'url': f'underline {c.info}',  # URLs
            
            # Prompt elements
            'prompt_symbol': f'bold {c.prompt_symbol}',
            'exit_code_ok': c.exit_code_ok,
            'exit_code_err': c.exit_code_err,
            'git_branch': c.info,
            'venv': c.info,
            
            # Status
            'error': c.error,
            'warning': c.warning,
            
            # Right prompt
            'rprompt': c.comment,
            'duration': c.warning,
        })

    def _setup_prompt_session(self):
        """Setup prompt_toolkit session with history, lexer and completer."""
        history = FileHistory(self.history_file) if self.config.history.enable else None
        
        # Build style from config colors
        self.style = self._build_style()
        
        # Setup Key Bindings
        from prompt_toolkit.key_binding import KeyBindings
        kb = KeyBindings()


        @kb.add('c-c')
        def _(event):
            self._interrupted = True
            event.app.exit(exception=KeyboardInterrupt)
        
        @kb.add('c-r')
        async def _(event):
            from axonix.ui.search import FuzzyHistorySearch
            
            # Get history from session
            history_items = []
            if self.session.history:
                history_items = list(self.session.history.get_strings())
            
            # Combine with in-memory context history (newest first for UI logic handling)
            combined = history_items + self.context.history
            
            searcher = FuzzyHistorySearch(combined)
            result = await searcher.run_async()
            
            if result:
                event.current_buffer.text = result
                event.current_buffer.cursor_position = len(result)

        self.session = PromptSession(
            history=history,
            lexer=AxonixLexer(self),
            completer=AxonixCompleter(self),
            style=self.style,
            complete_while_typing=True,
            key_bindings=kb
        )

    def _setup_signal_handlers(self):
        def sigint_handler(signum, frame):
            self._interrupted = True
            self._clear_current_line()
            try:
                self.session.app.invalidate()
            except Exception:
                pass

        def sigterm_handler(signum, frame):
            print("\nTerminated")
            self._close_shell()
            sys.exit(0)

        signal.signal(signal.SIGINT, sigint_handler)
        signal.signal(signal.SIGTERM, sigterm_handler)

        signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        signal.signal(signal.SIGTTIN, signal.SIG_IGN)
        signal.signal(signal.SIGTSTP, signal.SIG_IGN)


    def _close_shell(self):
        try:
            termios.tcsetattr(
                self._tty_fd,
                termios.TCSANOW,
                self._orig_term_attrs
            )
        except Exception:
            pass

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

    def _format_duration(self, seconds: float) -> str:
        """Format duration for display."""
        if seconds < 0.001:
            return ""  # Don't show for very fast commands
        elif seconds < 1:
            return f"{int(seconds * 1000)}ms"
        elif seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m{secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h{mins}m"

    def _get_rprompt(self) -> list:
        """Build right prompt with time and command duration."""
        parts = []
        
        # Show command duration if significant
        if self._last_command_duration is not None and self._last_command_duration >= 0.1:
            duration_str = self._format_duration(self._last_command_duration)
            if duration_str:
                parts.append(('class:duration', f"⏱ {duration_str} "))
        
        # Show current time
        current_time = datetime.now().strftime("%H:%M:%S")
        parts.append(('class:rprompt', current_time))
        
        return parts

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

        # Build right prompt
        rprompt = self._get_rprompt() if self.config.input.rprompt else None

        return self.session.prompt(prompt_html, rprompt=rprompt)

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
        """Execute a single pipeline using process groups."""

        processes = []
        pipe_fds = []
        prev_pipe_read = None
        exit_code = 0
        pgid = None
        has_external = False  # ⭐ ВАЖНО

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

                is_last = i == len(pipeline) - 1
                current_stdin = prev_pipe_read if i > 0 else None

                if stdin_file:
                    fd_in = os.open(stdin_file, os.O_RDONLY)
                    if current_stdin is not None:
                        safe_close(current_stdin)
                    current_stdin = fd_in

                current_stdout = None
                pipe_read = pipe_write = None

                if not is_last:
                    pipe_read, pipe_write = os.pipe()
                    pipe_fds.extend([pipe_read, pipe_write])
                    current_stdout = pipe_write

                if stdout_file:
                    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
                    fd_out = os.open(stdout_file, flags, 0o644)
                    if current_stdout is not None:
                        safe_close(current_stdout)
                        safe_close(pipe_read)
                        pipe_read = None
                    current_stdout = fd_out

                command = self.commands.get(cmd_name)

                if command:
                    thread = self.executor.execute_builtin(
                        command, args, current_stdin, current_stdout
                    )
                    processes.append(thread)
                else:
                    process = self.executor.execute_external(
                        cmd_name,
                        args,
                        current_stdin,
                        current_stdout,
                        pgid=pgid,
                    )

                    if pgid is None:
                        pgid = process.pid

                    has_external = True
                    processes.append(process)

                safe_close(current_stdout)
                safe_close(current_stdin)
                prev_pipe_read = pipe_read

            if has_external and pgid is not None:
                try:
                    os.tcsetpgrp(self._tty_fd, pgid)
                except Exception:
                    pass

            for idx, p in enumerate(processes):
                is_last = idx == len(processes) - 1
                if isinstance(p, threading.Thread):
                    p.join()
                    if is_last:
                        exit_code = self.context.last_exit_code
                else:
                    exit_code = p.wait()

                    if is_last:
                        if exit_code < 0:
                            exit_code = 128 + (-exit_code)

                        self.context.last_exit_code = exit_code

            return exit_code

        finally:
            if has_external:
                try:
                    os.tcsetpgrp(self._tty_fd, self._shell_pgid)
                except Exception:
                    pass

            self.executor.clear_finished()

            for fd in pipe_fds:
                safe_close(fd)

            if prev_pipe_read is not None:
                safe_close(prev_pipe_read)

    def run(self):
        try:
            while self.context.running:
                try:
                    try:
                        user_input = self._get_input()

                        if self._interrupted:
                            self._interrupted = False
                            continue

                    except KeyboardInterrupt:
                        self._interrupted = False
                        continue

                    except EOFError:
                        return

                    # Measure command execution time
                    start_time = time.perf_counter()
                    self._execute_line(user_input)
                    end_time = time.perf_counter()

                    self._last_command_duration = end_time - start_time

                except Exception as e:
                    print(f"Internal error: {e}")
                    self._last_command_duration = None
        finally:
            # Always restore termios attrs / clean up child processes,
            # whether we exit via Ctrl-D, `exit`, an unhandled exception,
            # or normal `running = False`. Previously this only ran on
            # SIGTERM, leaving the user's terminal in a half-broken state
            # after Ctrl-D (no echo of typed control chars).
            self._close_shell()

