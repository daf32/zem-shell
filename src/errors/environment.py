from src.errors.base import CLIError

class EnvironmentError(CLIError):
    exit_code = 4


class ConfigNotFoundError(EnvironmentError):
    def __init__(self, path):
        super().__init__(f"Config file not found: {path}")