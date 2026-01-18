from axonix.errors.base_error import CLIError

class ShellEnvironmentError(CLIError):
    exit_code = 4


class ConfigNotFoundError(ShellEnvironmentError):
    def __init__(self, path):
        super().__init__(f"Config file not found: {path}")