from src.errors.base import CLIError

class ExecutionError(CLIError):
    exit_code = 3

class CommandFailedError(ExecutionError):
    def __init__(self, command, reason=None):
        msg = f"Command failed: {command}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)
