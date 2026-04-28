"""Command executor with proper resource management."""
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from typing import Optional, Protocol, TextIO, Union, cast

from axonix.builtins.base import BaseCommand
from axonix.core.context import ExecutionContext
from axonix.errors.base_error import CLIError


class ProcessResult(Protocol):
    """Protocol for process-like objects."""
    def wait(self) -> int:
        """Wait for process to complete and return exit code."""
        ...


@contextmanager
def managed_fd(fd: Optional[int], mode: str = "r"):
    """Context manager for file descriptors."""
    if fd is None:
        yield None
        return
    
    try:
        f = os.fdopen(fd, mode)
        yield f
    finally:
        try:
            f.close()
        except (OSError, AttributeError):
            pass


class CommandExecutor:
    """Executes commands with proper resource management."""

    def __init__(self, context: ExecutionContext):
        self.context = context
        self._active_processes: list[Union[subprocess.Popen, threading.Thread]] = []
        self.logger = logging.getLogger("axonix.executor")

    def _get_fresh_path(self) -> str:
        """Get fresh PATH from the parent shell."""
        try:
            shell = os.environ.get('SHELL', '/bin/zsh')
            # Try to source the shell's rc file to get updated PATH
            rc_file = '~/.zshrc' if shell.endswith('zsh') else '~/.bashrc'
            command = f'source {rc_file} && echo $PATH'
            result = subprocess.run(
                [shell, '-c', command],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                fresh_path = result.stdout.strip()
                if fresh_path:
                    return fresh_path
            # If sourcing fails, try without sourcing
            result = subprocess.run(
                [shell, '-c', 'echo $PATH'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode == 0:
                fresh_path = result.stdout.strip()
                if fresh_path:
                    return fresh_path
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            pass
        # Fallback to current PATH
        return os.environ.get('PATH', '')
    
    def execute_builtin(
        self,
        command: BaseCommand,
        args: list[str],
        stdin_fd: Optional[int] = None,
        stdout_fd: Optional[int] = None,
    ) -> threading.Thread:
        """Execute a builtin command in a thread with proper resource management."""
        
        def run_command():
            stdin_obj: Optional[TextIO] = sys.stdin
            stdout_obj: Optional[TextIO] = sys.stdout
            
            try:
                with managed_fd(stdin_fd, "r") as stdin_file:
                    if stdin_file is not None:
                        stdin_obj = cast(TextIO, stdin_file)
                    
                    with managed_fd(stdout_fd, "w") as stdout_file:
                        if stdout_file is not None:
                            stdout_obj = cast(TextIO, stdout_file)
                        
                        try:
                            command.execute(args, self.context, stdin=stdin_obj, stdout=stdout_obj)
                        except BrokenPipeError:
                            # Broken pipe is expected in pipelines when consumer stops reading
                            pass
                        except CLIError as e:
                            # CLIErrors are user-facing and should be printed
                            self.context.last_exit_code = getattr(e, "exit_code", 1)
                            if stdout_obj:
                                stdout_obj.write(f"{e}\n")
                            else:
                                sys.stderr.write(f"{e}\n")
                        except Exception as e:
                            self.context.last_exit_code = 1
                            self.logger.error(f"Error in {command.name}: {e}")
                            sys.stderr.write(f"Error in {command.name}: {e}\n")
            except OSError as e:
                self.context.last_exit_code = 1
                self.logger.error(f"IO error in {command.name}: {e}")
                sys.stderr.write(f"IO error in {command.name}: {e}\n")
        
        # Use daemon=True so threads don't prevent shell shutdown
        # Threads are explicitly joined in _execute_pipeline, so this is safe
        thread = threading.Thread(target=run_command, daemon=True)
        self._active_processes.append(thread)
        thread.start()
        return thread
    
    def execute_external(
        self,
        cmd_name: str,
        args: list[str],
        stdin_fd: Optional[int] = None,
        stdout_fd: Optional[int] = None,
        pgid: Optional[int] = None,
    ) -> subprocess.Popen:
        if not cmd_name or not isinstance(cmd_name, str):
            raise ValueError(f"Invalid command name: {cmd_name}")

        sanitized_args = [str(arg) for arg in args]

        old_handler = signal.getsignal(signal.SIGINT)

        try:
            # Shell ignores Ctrl+C while command runs
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            # Get fresh environment with updated PATH
            env = os.environ.copy()
            fresh_path = self._get_fresh_path()
            if fresh_path:
                env['PATH'] = fresh_path

            def preexec():
                # Create or join process group
                if pgid is None:
                    os.setpgid(0, 0)
                else:
                    os.setpgid(0, pgid)

                # Child receives Ctrl+C
                signal.signal(signal.SIGINT, signal.SIG_DFL)

            process = subprocess.Popen(
                [cmd_name] + sanitized_args,
                stdin=stdin_fd,
                stdout=stdout_fd,
                env=env,
                preexec_fn=preexec,
            )

            self._active_processes.append(process)
            return process

        finally:
            signal.signal(signal.SIGINT, old_handler)
    
    def clear_finished(self):
        """Remove finished processes and threads from the active list."""
        still_running = []
        for p in self._active_processes:
            if isinstance(p, subprocess.Popen):
                if p.poll() is None:
                    still_running.append(p)
            elif isinstance(p, threading.Thread):
                if p.is_alive():
                    still_running.append(p)
        self._active_processes = still_running

    def cleanup_processes(self):
        """Clean up all active processes."""
        self.logger.debug(f"Cleaning up {len(self._active_processes)} processes")
        for process in self._active_processes:
            if isinstance(process, subprocess.Popen):
                try:
                    process.terminate()
                    # Wait with timeout manually
                    start_time = time.time()
                    while process.poll() is None and (time.time() - start_time) < 1:
                        time.sleep(0.1)
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                except Exception as e:
                    self.logger.warning(f"Error cleaning up process: {e}")
            elif isinstance(process, threading.Thread):
                if process.is_alive():
                    # Threads can't be forcefully killed, just wait
                    process.join(timeout=1)
        
        self._active_processes.clear()
