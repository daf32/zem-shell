from psh.errors.base_error import CLIError

class InputError(CLIError):
    def __init__(self, e):
        super().__init__(str(e))
    exit_code = 2

class UnknownCommandError(InputError):
    def __init__(self, command):
        super().__init__(f"Unknown command '{command}'")

class ArgumentError(InputError):
    def __init__(self, command, arguments, reason=None):
        if isinstance(arguments, list):
            args_str = " ".join(map(str, arguments))
        else:
            args_str = str(arguments)
        
        msg = f"{command}: Invalid argument(s) '{args_str}'"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)