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

    @staticmethod
    def _dup(fd: Optional[int]) -> Optional[int]:
        return os.dup(fd) if fd is not None else None

    def _run_builtin(
        self,
        command: BaseCommand,
        args: list[str],
        stdin_fd: Optional[int],
        stdout_fd: Optional[int],
        stderr_fd: Optional[int] = None,
    ) -> int:
        """Run ``command`` synchronously and return its exit code.

        Takes ownership of the given fds (they are closed on return). Any
        ``None`` stream falls back to the process-level ``sys.*`` stream.
        """
        stdin_obj: Optional[TextIO] = sys.stdin
        stdout_obj: Optional[TextIO] = sys.stdout
        stderr_obj: Optional[TextIO] = sys.stderr

        exit_code = 0
        try:
            with managed_fd(stdin_fd, "r") as stdin_file, \
                    managed_fd(stdout_fd, "w") as stdout_file, \
                    managed_fd(stderr_fd, "w") as stderr_file:
                if stdin_file is not None:
                    stdin_obj = cast(TextIO, stdin_file)
                if stdout_file is not None:
                    stdout_obj = cast(TextIO, stdout_file)
                if stderr_file is not None:
                    stderr_obj = cast(TextIO, stderr_file)

                kwargs = {"stdin": stdin_obj, "stdout": stdout_obj}
                if command._accepts_stderr:
                    kwargs["stderr"] = stderr_obj

                try:
                    ret = command.execute(args, self.context, **kwargs)
                    # Backward compat: legacy builtins return None.
                    exit_code = int(ret) if ret is not None else 0
                except BrokenPipeError:
                    # Expected in pipelines when the consumer stops reading.
                    exit_code = 0
                except KeyboardInterrupt:
                    exit_code = 130
                except CLIError as e:
                    exit_code = getattr(e, "exit_code", 1)
                    stderr_obj.write(f"{e}\n")
                except Exception as e:
                    exit_code = 1
                    self.logger.error(f"Error in {command.name}: {e}")
                    stderr_obj.write(f"Error in {command.name}: {e}\n")
                finally:
                    try:
                        stdout_obj.flush()
                        stderr_obj.flush()
                    except (OSError, ValueError):
                        pass
        except OSError as e:
            exit_code = 1
            self.logger.error(f"IO error in {command.name}: {e}")
            sys.stderr.write(f"IO error in {command.name}: {e}\n")
        return exit_code

    def run_builtin_inline(
        self,
        command: BaseCommand,
        args: list[str],
        stdin_fd: Optional[int] = None,
        stdout_fd: Optional[int] = None,
        stderr_fd: Optional[int] = None,
    ) -> int:
        """Run a builtin on the calling (main) thread.

        Used for single-stage pipelines and for ``main_thread_only``
        commands. The caller keeps ownership of its fds; duplicates are
        handed to the builtin.
        """
        return self._run_builtin(
            command, args, self._dup(stdin_fd), self._dup(stdout_fd), self._dup(stderr_fd)
        )

    def execute_builtin(
        self,
        command: BaseCommand,
        args: list[str],
        stdin_fd: Optional[int] = None,
        stdout_fd: Optional[int] = None,
        stderr_fd: Optional[int] = None,
    ) -> threading.Thread:
        """Execute a builtin in a worker thread (pipeline stages).

        The builtin's exit code is stashed on the returned ``Thread`` as a
        ``.exit_code`` attribute; the caller (``Shell._execute_pipeline``)
        reads it after ``join()`` and writes it to ``context.last_exit_code``
        from the main thread. This keeps the shared exit-code slot free of
        cross-thread races when multiple builtins run in the same pipeline.

        The worker takes ownership of *duplicates* of the caller's fds: the
        caller closes its own copies right after this call returns, so both
        sides can't race on the same descriptor.
        """
        in_fd, out_fd, err_fd = self._dup(stdin_fd), self._dup(stdout_fd), self._dup(stderr_fd)

        def run_command():
            try:
                thread.exit_code = self._run_builtin(  # type: ignore[attr-defined]
                    command, args, in_fd, out_fd, err_fd
                )
            except BaseException:
                thread.exit_code = 1  # type: ignore[attr-defined]
                raise

        # Use daemon=True so threads don't prevent shell shutdown.
        # Threads are explicitly joined in _execute_pipeline, so this is safe.
        thread = threading.Thread(target=run_command, daemon=True)
        thread.exit_code = 0  # type: ignore[attr-defined]
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
        stderr_fd: Optional[int] = None,
    ) -> subprocess.Popen:
        if not cmd_name or not isinstance(cmd_name, str):
            raise ValueError(f"Invalid command name: {cmd_name}")

        # Resolve once up-front so missing binaries surface as a clean
        # UnknownCommandError instead of leaking through Popen's preexec
        # path (where the child error can be reported as ENOENT, ENAMETOOLONG,
        # or other OSError codes depending on platform/sandbox).
        import shutil

        from axonix.errors.input_error import UnknownCommandError
        if "/" not in cmd_name and shutil.which(cmd_name) is None:
            raise UnknownCommandError(cmd_name)

        sanitized_args = [str(arg) for arg in args]

        old_handler = signal.getsignal(signal.SIGINT)

        try:
            # Shell ignores Ctrl+C while command runs
            signal.signal(signal.SIGINT, signal.SIG_IGN)

            # Children see exported variables only (see ExecutionContext).
            env = self.context.child_env()

            def preexec():
                # Create or join process group
                if pgid is None:
                    os.setpgid(0, 0)
                else:
                    os.setpgid(0, pgid)

                # The shell ignores the job-control signals (and SIGINT
                # while spawning); ignored dispositions survive execve, so
                # reset them or the child could never be Ctrl-C'd/Ctrl-Z'd.
                for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTSTP,
                            signal.SIGTTIN, signal.SIGTTOU):
                    signal.signal(sig, signal.SIG_DFL)

            try:
                process = subprocess.Popen(
                    [cmd_name] + sanitized_args,
                    stdin=stdin_fd,
                    stdout=stdout_fd,
                    stderr=stderr_fd,
                    env=env,
                    preexec_fn=preexec,
                )
            except FileNotFoundError:
                # Surface as a normal user-facing CLI error (exit 2) instead of
                # the generic "internal error" path used by `except Exception`
                # in Shell._execute_line.
                from axonix.errors.input_error import UnknownCommandError
                raise UnknownCommandError(cmd_name) from None

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
