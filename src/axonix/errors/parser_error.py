from axonix.errors.base_error import CLIError


class ParseError(CLIError):
    def __init__(self, e):
        super().__init__(str(e))

class UnclosedQuoteError(ParseError):
    def __init__(self):
        super().__init__("Unclosed quote")