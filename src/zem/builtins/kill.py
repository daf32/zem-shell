import os
import signal

from zem.builtins.base import BaseCommand
from zem.core.jobs import JobState
from zem.errors.input_error import ArgumentError


def _parse_signal(text: str) -> int:
    name = text.upper()
    if name.isdigit():
        return int(name)
    if not name.startswith("SIG"):
        name = "SIG" + name
    try:
        return int(getattr(signal, name))
    except AttributeError:
        raise ArgumentError("kill", text, reason="unknown signal") from None


class KillCommand(BaseCommand):
    help = "Send a signal to a job or process"
    usage = "kill [-SIGNAL|-s SIGNAL] JOBSPEC|PID... | kill -l"
    examples = [
        "kill %1          - SIGTERM job 1",
        "kill -9 %1       - SIGKILL job 1",
        "kill -STOP 1234  - Stop pid 1234",
        "kill -l          - List signal names",
    ]
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        if args == ["-l"]:
            names = sorted(
                (s.name[3:] for s in signal.Signals if s.name.startswith("SIG")),
                key=lambda n: int(getattr(signal, "SIG" + n)),
            )
            self._write(" ".join(names) + "\n", stdout)
            return 0

        sig = signal.SIGTERM
        targets: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-s":
                if i + 1 >= len(args):
                    raise ArgumentError(self.name, arg, reason="expected SIGNAL")
                sig = _parse_signal(args[i + 1])
                i += 2
                continue
            if arg == "--":
                targets.extend(args[i + 1:])
                break
            if arg.startswith("-") and len(arg) > 1 and not targets:
                sig = _parse_signal(arg[1:])
            else:
                targets.append(arg)
            i += 1
        self._require_args(targets, min_count=1, error_msg="expected JOBSPEC or PID")

        table = context._jobs
        table.reap()
        status = 0
        for target in targets:
            try:
                if target.startswith("%"):
                    job = table.get(target)
                    os.killpg(job.pgid, sig)
                    # A stopped job can't act on TERM/HUP/INT until it runs.
                    if job.state is JobState.STOPPED and sig in (
                        signal.SIGTERM, signal.SIGHUP, signal.SIGINT
                    ):
                        os.killpg(job.pgid, signal.SIGCONT)
                else:
                    try:
                        pid = int(target)
                    except ValueError:
                        raise ArgumentError(self.name, target, reason="expected PID") from None
                    os.kill(pid, sig)
            except ProcessLookupError:
                self._write_err(f"kill: {target}: no such process\n", stderr)
                status = 1
            except PermissionError:
                self._write_err(f"kill: {target}: operation not permitted\n", stderr)
                status = 1
            except ArgumentError:
                raise
            except Exception as e:  # JobError etc.
                self._write_err(f"kill: {e}\n", stderr)
                status = 1
        return status
