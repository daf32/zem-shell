from src.errors.base import CLIError

class ParseError(CLIError):
    def __init__(self, e):
        super().__init__(f"ParseError: {e}")

class UnclosedQuoteError(ParseError):
    def __init__(self):
        super().__init__("Unclosed quote")