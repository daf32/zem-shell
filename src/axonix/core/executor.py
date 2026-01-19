"""Command executor with proper resource management."""
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from typing import Optional, Protocol, TextIO, Union

from axonix.builtins.base import BaseCommand
from axonix.core.context import ExecutionContext
from axonix.errors.base_error import CLIError
from axonix.utils.logger import get_logger


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
        self.logger = get_logger()
    
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
                        stdin_obj = stdin_file
                    
                    with managed_fd(stdout_fd, "w") as stdout_file:
                        if stdout_file is not None:
                            stdout_obj = stdout_file
                        
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
    ) -> subprocess.Popen:
        """Execute an external command with proper resource management."""
        # Validate command name to prevent command injection
        if not cmd_name or not isinstance(cmd_name, str):
            raise ValueError(f"Invalid command name: {cmd_name}")
        
        # Validate args
        if not isinstance(args, list):
            raise ValueError("Args must be a list")
        
        # Sanitize args - ensure all are strings
        sanitized_args = [str(arg) for arg in args]
        
        try:
            process = subprocess.Popen(
                [cmd_name] + sanitized_args,
                stdin=stdin_fd,
                stdout=stdout_fd,
                stderr=subprocess.PIPE,  # Capture stderr separately
            )
            self._active_processes.append(process)
            return process
        except FileNotFoundError:
            raise FileNotFoundError(f"Command not found: {cmd_name}")
        except ValueError as e:
            raise ValueError(f"Invalid arguments for {cmd_name}: {e}")
    
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
