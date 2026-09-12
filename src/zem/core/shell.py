import os
import signal
import subprocess
import sys
import termios
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles import Style

from zem.builtins import DEFAULT_USER_PLUGINS_DIR, load_plugins
from zem.builtins.base import BaseCommand
from zem.builtins.registry import CommandRegistry
from zem.config.settings import AppConfig
from zem.core.context import ExecutionContext
from zem.core.executor import CommandExecutor
from zem.core.history_expand import expand_history
from zem.core.jobs import Job, JobState, exit_code_from, format_notice, wait_process
from zem.core.parser import Parser
from zem.core.scan import join_lines
from zem.errors.base_error import CLIError
from zem.errors.execute_error import ExecutionError
from zem.errors.parser_error import ParseError
from zem.ui.completer import ZemCompleter
from zem.ui.history import ZemFileHistory
from zem.ui.lexer import ZemLexer
from zem.utils.git import format_git_branch, get_git_info
from zem.utils.venv import activate_venv, get_venv_info


class Shell:
    HISTORY_FILE = os.path.expanduser("~/.zem_history")
    RC_FILE = os.path.expanduser("~/.zemrc")
    
    def __init__(
        self,
        commands: Optional[Dict[str, BaseCommand]] = None,
        config: Optional[AppConfig] = None,
        headless: bool = False,
        user_plugins_dir: str | None = DEFAULT_USER_PLUGINS_DIR,
    ):
        """Construct a shell instance.

        ``headless=True`` skips everything that requires a real TTY:
        ``prompt_toolkit`` session setup, signal handlers, and the
        ``termios``/``tcsetpgrp`` plumbing. Use it from tests, where
        ``sys.stdin`` is a captured pseudo-file with no ``fileno()``.
        Pipelines built from ``Parser`` plus ``Executor`` still work in
        headless mode — only the interactive REPL path (``Shell.run``)
        is unavailable.

        ``user_plugins_dir`` is where external plugins are imported from
        (``~/.zem/plugins`` by default); ``None`` disables them. Only
        consulted when ``commands`` is ``None``.
        """
        self.config = config or AppConfig()
        self.context = ExecutionContext()
        self.history_file = self.config.history.file
        self.rc_file = self.config.rc.file
        self.headless = headless

        if commands is None:
            load_plugins(user_plugins_dir)
            self.commands = CommandRegistry.get_all_commands()
        else:
            self.commands = commands

        self.context.commands = self.commands
        self.executor = CommandExecutor(self.context)

        self.context._shell = self
        self._last_command_duration: Optional[float] = None  # Duration in seconds
        self._interrupted = False

        if not headless:
            self._setup_prompt_session()
            self._setup_signal_handlers()

        if self.config.rc.auto_create and not os.path.exists(self.rc_file):
            self._create_default_rc()

        self._load_rc_file()

        if self.config.venv.auto:
            activate_venv(self.context)

        self._sync_plugin_configs()

        if headless:
            # Sentinel values; nothing reads them except `_close_shell`,
            # which guards on `headless` too.
            self._shell_pgid = -1
            self._tty_fd = -1
            self._orig_term_attrs = None
            return

        self._shell_pgid = os.getpgrp()
        self._tty_fd = sys.stdin.fileno()

        self._orig_term_attrs = termios.tcgetattr(self._tty_fd)

        new_attrs = termios.tcgetattr(self._tty_fd)
        new_attrs[3] = new_attrs[3] & ~termios.ECHOCTL
        termios.tcsetattr(self._tty_fd, termios.TCSANOW, new_attrs)

    def _sync_plugin_configs(self):
        """Sync default plugin configurations to the config file."""
        from zem.config.settings import get_config_path
        from zem.config.store import update_raw

        updated = False
        plugins_config = self.config.plugins.copy()
        
        for name, cmd in self.commands.items():
            defaults = cmd.get_default_config()
            if defaults and name not in plugins_config:
                plugins_config[name] = defaults
                updated = True
        
        if updated:
            def mutate(data: dict) -> None:
                section = data.setdefault("plugins", {})
                for k, v in plugins_config.items():
                    section.setdefault(k, v)

            try:
                update_raw(get_config_path(), mutate)
                self.config.plugins = plugins_config
            except Exception as e:
                print(f"Warning: Failed to sync plugin configs: {e}")

    def _create_default_rc(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(current_dir, "..", "resources", "zemrc.default")
        
        try:
            if os.path.isfile(template_path):
                import shutil
                shutil.copy(template_path, self.rc_file)
            else:
                with open(self.rc_file, "w", encoding="utf-8") as f:
                    f.write("# Zem Shell (Minimal Config)\n")
                    f.write("set SHELL zem\n")
                    f.write("alias help='help'\n")
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to create default {self.rc_file}: {e}\n")

    def _load_rc_file(self):
        if os.path.exists(self.rc_file):
            self._run_script_file(self.rc_file)

    def _run_script_lines(self, lines) -> int:
        """Execute ``lines`` as a script (rc file, `source`).

        Blank lines and `#` comment lines are skipped; a line that needs
        continuation (trailing `\\`, open quote, trailing operator) is
        joined with the following one. Each logical line runs through
        `_execute_line` without touching history; execution continues past
        errors like an interactive bash `source`. Returns the last exit code.
        """
        buffer: str | None = None
        for raw in lines:
            line = raw.rstrip("\n")
            if buffer is None:
                if not line.strip() or line.lstrip().startswith(self.config.operators.comment):
                    continue
                buffer = line
            else:
                buffer = join_lines(buffer, line, self.config.operators)
            if not Parser.needs_continuation(buffer, self.config):
                self._execute_line(buffer, add_to_history=False)
                buffer = None
        if buffer is not None:
            self._execute_line(buffer, add_to_history=False)
        return self.context.last_exit_code

    def _run_script_file(self, path: str) -> int:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return self._run_script_lines(f)
        except OSError as e:
            self._print_error(f"{path}: {e.strerror}")
            self.context.last_exit_code = 1
            return 1

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

            # fish-style ghost text from history
            'auto-suggestion': c.comment,
        })

    def _setup_prompt_session(self):
        """Setup prompt_toolkit session with history, lexer and completer."""
        history = ZemFileHistory(self.history_file) if self.config.history.enable else None
        
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
            from zem.ui.search import FuzzyHistorySearch
            
            # Get history from session
            history_items = []
            if self.session.history:
                history_items = list(self.session.history.get_strings())
            
            # Combine with in-memory context history (newest first for UI logic handling)
            combined = history_items + self.context.history
            
            searcher = FuzzyHistorySearch(combined, self.config.colors)
            result = await searcher.run_async()
            
            if result:
                event.current_buffer.text = result
                event.current_buffer.cursor_position = len(result)

        auto_suggest = AutoSuggestFromHistory() if self.config.input.auto_suggest else None
        self.session = PromptSession(
            history=history,
            lexer=ZemLexer(self),
            completer=ZemCompleter(self),
            auto_suggest=auto_suggest,
            style=self.style,
            complete_while_typing=True,
            # Hint specs may shell out (git branches, docker containers).
            # On the event loop thread that would freeze rendering on every
            # keystroke; in a worker it is also cancelled when the next one
            # arrives.
            complete_in_thread=True,
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


    def _restore_terminal(self):
        """Put the tty back the way we found it (also used by `exec`)."""
        if not self.headless and self._orig_term_attrs is not None:
            try:
                termios.tcsetattr(
                    self._tty_fd,
                    termios.TCSANOW,
                    self._orig_term_attrs
                )
            except Exception:
                pass

    def _close_shell(self):
        self._restore_terminal()

        # Like bash: remaining jobs get SIGHUP (and SIGCONT so stopped ones
        # can act on it) before we tear the rest down.
        for job in list(self.context._jobs):
            for sig in (signal.SIGHUP, signal.SIGCONT):
                try:
                    os.killpg(job.pgid, sig)
                except OSError:
                    pass
            self.context._jobs.remove(job)

        self.executor.cleanup_processes()
        self.context.running = False
        if not self.headless:
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

    def _build_colored_prompt(
        self, venv_info: str | None, path: str, git_info: str, exit_code: int
    ) -> list:
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

    def _build_text_prompt(
        self, venv_info: str | None, path: str, git_info: str, exit_code: int
    ) -> str:
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
        lexer = getattr(self.session, "lexer", None)
        if hasattr(lexer, "clear_path_cache"):
            lexer.clear_path_cache()
        real_cwd = os.getcwd()
        display_path = self._format_path(real_cwd)
        exit_code = self.context.last_exit_code
        
        git_display = ""
        if getattr(self.config.input, "show_git_info", False):
            git_info = get_git_info(real_cwd)
            if git_info:
                branch, status = git_info
                git_display = f" ({format_git_branch(branch, status)})"

        show_venv = getattr(self.config.input, "show_venv_info", False)
        venv_display = get_venv_info() if show_venv else None

        if self.config.input.color_prompt:
            prompt_html = self._build_colored_prompt(
                venv_display, display_path, git_display, exit_code
            )
        else:
            prompt_html = self._build_text_prompt(
                venv_display, display_path, git_display, exit_code
            )

        # Build right prompt
        rprompt = self._get_rprompt() if self.config.input.rprompt else None

        text = self.session.prompt(prompt_html, rprompt=rprompt)
        while Parser.needs_continuation(text, self.config):
            more = self.session.prompt([("class:prompt_symbol", "> ")])
            text = join_lines(text, more, self.config.operators)
        return text

    def _print_error(self, message: str):
        from prompt_toolkit import HTML, print_formatted_text

        from zem.utils.colors import error_tag
        print_formatted_text(HTML(f'{error_tag(self.config)} {message}'), file=sys.stderr)

    # -- job control ---------------------------------------------------------

    def _give_terminal(self, pgid: int) -> None:
        if self.headless:
            return
        try:
            os.tcsetpgrp(self._tty_fd, pgid)
        except OSError:
            pass

    def _reclaim_terminal(self) -> None:
        if self.headless:
            return
        try:
            os.tcsetpgrp(self._tty_fd, self._shell_pgid)
        except OSError:
            pass

    def _notify(self, line: str) -> None:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()

    def _report_jobs(self) -> None:
        """Print state changes of background jobs (called before each prompt)."""
        for job in self.context._jobs.reap():
            marker = "+" if self.context._jobs.current() is job else " "
            self._notify(format_notice(job, marker))

    def _wait_job(self, job: Job, *, foreground: bool = True) -> int:
        """Block until ``job`` finishes or stops; return its exit code.

        A stop (Ctrl-Z / SIGSTOP) leaves the job in the table as Stopped
        and returns 128 + SIGTSTP like bash.
        """
        if foreground:
            self._give_terminal(job.pgid)
        try:
            for idx, proc in enumerate(job.procs):
                while True:
                    state, value = wait_process(proc)
                    if state == "stopped":
                        job.state = JobState.STOPPED
                        job.notified = True  # we print it right here
                        self.context._jobs._touch(job)
                        self._notify(format_notice(job, "+"))
                        return exit_code_from("stopped", value)
                    if state != "running":
                        job._codes[idx] = exit_code_from(state, value)
                        break
            job.state = JobState.DONE
            job.exit_code = job.last_code
            self.context._jobs.remove(job)
            return job.exit_code
        finally:
            if foreground:
                self._reclaim_terminal()

    @staticmethod
    def _pipeline_text(pipeline: list[dict]) -> str:
        import shlex
        return " | ".join(shlex.join([c["name"], *c["args"]]) for c in pipeline)

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

        if add_to_history and self.config.history.expand:
            try:
                user_input, changed = expand_history(
                    user_input, self.context.history, self.config.operators
                )
            except CLIError as e:
                self.context.last_exit_code = getattr(e, "exit_code", 1)
                self._print_error(str(e))
                return
            if changed:
                # bash echoes the expanded line so the user sees what ran.
                sys.stdout.write(user_input + "\n")
                sys.stdout.flush()

        if add_to_history:
            self._add_history(user_input)

        try:
            self._execute_units(self._parser(user_input).iter_units())
        except CLIError as e:
            self.context.last_exit_code = getattr(e, "exit_code", 1)
            self._print_error(str(e))
        except Exception as e:
            self.context.last_exit_code = 1
            self._print_error(f"internal error: {e}")



    def _parser(self, text: str) -> Parser:
        return Parser(
            text,
            self.context.variables,
            self.context.aliases,
            self.config,
            substitutor=self._capture_output,
        )

    def _execute_units(
        self,
        units,
        *,
        final_stdout_fd: int | None = None,
        forbid_background: bool = False,
    ) -> int:
        """Run parsed units honouring `&&`, `||`, `;`. Returns the last exit code.

        ``units`` may be a lazy iterator (see `Parser.iter_units`): each
        unit is expanded right before it runs, so `$?` reflects the
        previous unit on the same line. ``final_stdout_fd`` redirects the
        stdout of every pipeline's last stage (used by command
        substitution).
        """
        last_exit_code = 0
        for unit in units:
            if forbid_background and unit["pipeline"][-1].get("background"):
                raise ParseError("Background jobs are not allowed inside $(...)")
            last_exit_code = self._execute_pipeline(
                unit["pipeline"], final_stdout_fd=final_stdout_fd
            )
            self.context.last_exit_code = last_exit_code

            logic = unit["logic"]
            if logic == "&&" and last_exit_code != 0:
                break
            if logic == "||" and last_exit_code == 0:
                break
            # `;` continues regardless of exit code
        return last_exit_code

    def _capture_output(self, text: str) -> str:
        """Run ``text`` and return its stdout — the engine behind ``$(...)``.

        Nested substitutions work because the parser is handed this same
        method. The output is drained by a helper thread so producers
        writing more than the pipe buffer can hold don't deadlock against
        the synchronous wait in `_execute_pipeline`. The last exit code is
        restored afterwards, so `$?` reflects the enclosing command.
        """
        units = self._parser(text).iter_units()

        read_fd, write_fd = os.pipe()
        chunks: list[bytes] = []

        def drain():
            with os.fdopen(read_fd, "rb") as reader:
                chunks.append(reader.read())

        reader_thread = threading.Thread(target=drain, daemon=True)
        reader_thread.start()

        saved_exit_code = self.context.last_exit_code
        try:
            self._execute_units(units, final_stdout_fd=write_fd, forbid_background=True)
        finally:
            os.close(write_fd)
            reader_thread.join()
            self.context.last_exit_code = saved_exit_code

        return b"".join(chunks).decode("utf-8", errors="replace")

    def _execute_pipeline(self, pipeline: list[dict], *, final_stdout_fd: int | None = None) -> int:
        """Execute a single pipeline using process groups."""

        processes = []
        prev_pipe_read = None
        exit_code = 0
        pgid = None
        has_external = False
        # Honour `&` only when it terminates a pipeline whose last stage is an
        # external process; backgrounding a pure-builtin pipeline doesn't make
        # sense (builtins run in this process and would still mutate context).
        is_background = bool(pipeline and pipeline[-1].get("background"))

        if len(pipeline) > 1:
            for cmd_info in pipeline:
                if cmd_info.get("force_external"):
                    continue
                cmd = self.commands.get(cmd_info["name"])
                if cmd is not None and cmd.main_thread_only:
                    raise ExecutionError(f"{cmd.name}: cannot be used in a pipeline")

        # Every fd this method opens is tracked here and closed exactly once:
        # fd numbers get reused immediately, so a second close would hit
        # whatever was opened in between (e.g. a worker thread's dup).
        open_fds: set[int] = set()

        def track(fd: int) -> int:
            open_fds.add(fd)
            return fd

        def close(fd: int | None) -> None:
            if fd is None or fd not in open_fds:
                return
            open_fds.discard(fd)
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
                stderr_file = cmd_info.get("stderr_file")
                stderr_append = cmd_info.get("stderr_append", False)
                stderr_to_stdout = cmd_info.get("stderr_to_stdout", False)

                is_last = i == len(pipeline) - 1
                current_stdin = prev_pipe_read if i > 0 else None
                prev_pipe_read = None

                if stdin_file:
                    close(current_stdin)
                    current_stdin = track(os.open(stdin_file, os.O_RDONLY))

                current_stdout = None
                pipe_read = None

                if not is_last:
                    pipe_read, pipe_write = os.pipe()
                    track(pipe_read)
                    current_stdout = track(pipe_write)

                if stdout_file:
                    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
                    fd_out = os.open(stdout_file, flags, 0o644)
                    close(current_stdout)
                    close(pipe_read)
                    pipe_read = None
                    current_stdout = track(fd_out)
                elif is_last and final_stdout_fd is not None:
                    # Command substitution: the caller owns `final_stdout_fd`;
                    # hand this stage its own copy so the usual close is safe.
                    current_stdout = track(os.dup(final_stdout_fd))

                current_stderr = None
                if stderr_file:
                    flags = os.O_WRONLY | os.O_CREAT | (
                        os.O_APPEND if stderr_append else os.O_TRUNC
                    )
                    current_stderr = track(os.open(stderr_file, flags, 0o644))
                elif stderr_to_stdout and current_stdout is not None:
                    # `2>&1` / `&>`: stderr shares stdout's destination. When
                    # stdout is the terminal there is nothing to duplicate.
                    current_stderr = track(os.dup(current_stdout))

                command = None if cmd_info.get("force_external") else self.commands.get(cmd_name)

                if command and len(pipeline) == 1:
                    # Single builtin: run inline on the main thread. Needed
                    # for `main_thread_only` commands and avoids a thread
                    # round-trip for the common `cd`/`set`/... case.
                    exit_code = self.executor.run_builtin_inline(
                        command, args, current_stdin, current_stdout, current_stderr
                    )
                    self.context.last_exit_code = exit_code
                    return exit_code

                if command:
                    thread = self.executor.execute_builtin(
                        command, args, current_stdin, current_stdout, current_stderr
                    )
                    processes.append(thread)
                else:
                    process = self.executor.execute_external(
                        cmd_name,
                        args,
                        current_stdin,
                        current_stdout,
                        pgid=pgid,
                        stderr_fd=current_stderr,
                    )

                    if pgid is None:
                        pgid = process.pid

                    has_external = True
                    processes.append(process)

                # The stage owns duplicates (builtins) or inherited copies
                # (children); our originals must go so readers see EOF.
                close(current_stdout)
                close(current_stdin)
                close(current_stderr)
                prev_pipe_read = pipe_read

            procs = [p for p in processes if isinstance(p, subprocess.Popen)]
            threads = [p for p in processes if isinstance(p, threading.Thread)]

            if is_background and not has_external:
                # Backgrounding a pure-builtin pipeline isn't honoured; warn
                # and fall back to foreground execution to preserve correctness.
                self._print_error(
                    "background (`&`) is only supported for external commands; "
                    "running this pipeline in the foreground"
                )
                is_background = False

            if has_external and pgid is not None:
                job = self.context._jobs.add(pgid, self._pipeline_text(pipeline), procs)
                if is_background:
                    # Detach: `[N] pid` like bash; reaped before later prompts.
                    self._notify(f"[{job.id}] {job.pgid}")
                    for t in threads:
                        t.join()
                    exit_code = 0
                    self.context.last_exit_code = 0
                    return exit_code

                # Foreground: builtin stages finish on their own; the job's
                # exit code comes from its external stages (and wins when
                # the external is the last stage).
                for t in threads:
                    t.join()
                external_code = self._wait_job(job, foreground=True)
                last = processes[-1]
                if isinstance(last, threading.Thread):
                    exit_code = getattr(last, "exit_code", 0)
                else:
                    exit_code = external_code
                self.context.last_exit_code = exit_code
                return exit_code

            # Builtins only.
            for t in threads:
                t.join()
            if threads:
                # The builtin worker thread stashes its exit code on the
                # Thread object (see CommandExecutor.execute_builtin).
                exit_code = getattr(threads[-1], "exit_code", 0)
            self.context.last_exit_code = exit_code
            return exit_code

        finally:
            self.executor.clear_finished()

            # Anything still open here is a leftover from an early exit
            # (exception mid-pipeline, inline return).
            for fd in list(open_fds):
                close(fd)

    def run(self) -> int:
        """Run the interactive loop; returns the shell's exit status."""
        try:
            while self.context.running:
                try:
                    self._report_jobs()
                    try:
                        user_input = self._get_input()

                        if self._interrupted:
                            self._interrupted = False
                            continue

                    except KeyboardInterrupt:
                        self._interrupted = False
                        continue

                    except EOFError:
                        return self.context.exit_status

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
        return self.context.exit_status

