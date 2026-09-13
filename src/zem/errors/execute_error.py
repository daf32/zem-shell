from zem.errors.base_error import CLIError


class ExecutionError(CLIError):
    exit_code = 3
