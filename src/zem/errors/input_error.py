from zem.errors.base_error import CLIError


class InputError(CLIError):
    def __init__(self, e):
        super().__init__(str(e))
    exit_code = 2

class UnknownCommandError(InputError):
    """A name that is neither a builtin, an alias, nor on PATH.

    127 is what every other shell answers here, and what scripts and
    wrappers check for; 2 belongs to a command that was found and used
    wrongly.
    """

    exit_code = 127

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