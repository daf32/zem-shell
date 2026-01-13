import re
from src.symbols import Operators
from src.errors.parser import ParseError, UnclosedQuoteError

_VAR_OP_ESCAPED = re.escape(Operators.variable.value)
_VAR_PATTERN = re.compile(rf'{_VAR_OP_ESCAPED}(\w+|\{{[^}}]+\}})')

class Parser:
    def __init__(self, text: str, variables: dict):
        self.tokens = self._get_tokens(text)
        self.variables = variables

    def _expand_variables_in_string(self, s: str) -> str:
        placeholder = '\0'
        s = s.replace(f"\\{Operators.variable.value}", placeholder)

        def repl(m):
            name = m.group(1)
            if name.startswith('{') and name.endswith('}'):
                name = name[1:-1]
            val = self.variables.get(name, "")
            return str(val)

        result = _VAR_PATTERN.sub(repl, s)
        return result.replace(placeholder, Operators.variable.value)
    
    def _get_tokens(self, text) -> list:
        NORMAL, SINGLE, DOUBLE = range(3)

        tokens: list[tuple[str, str | None]] = []
        current: list[str] = []
        state = NORMAL

        def flush(quote=None):
            if current:
                tokens.append(("".join(current), quote))
                current.clear()

        for ch in text:
            if state == NORMAL:
                if ch.isspace():
                    flush()
                elif ch == "'":
                    state = SINGLE
                elif ch == '"':
                    state = DOUBLE
                else:
                    current.append(ch)

            elif state == SINGLE:
                if ch == "'":
                    flush("'")
                    state = NORMAL
                else:
                    current.append(ch)

            elif state == DOUBLE:
                if ch == '"':
                    flush('"')
                    state = NORMAL
                else:
                    current.append(ch)

        if state != NORMAL:
            raise UnclosedQuoteError()

        flush()

        if not tokens:
            raise ParseError("zero tokens")
        
        return tokens

        return tokens

    def parse(self) -> tuple[str, list[str]]:
        final_tokens = []
        for tok, quote in self.tokens:
            if quote == "'":
                final = tok.replace(f"\\{Operators.variable.value}", Operators.variable.value)
            else:
                final = self._expand_variables_in_string(tok)
            final_tokens.append(final)
        
        if not final_tokens:
             raise ParseError("zero tokens")

        return final_tokens[0], final_tokens[1:]
