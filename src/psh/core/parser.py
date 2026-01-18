import re
from psh.config.settings import config
from psh.errors.parser_error import ParseError, UnclosedQuoteError

class Parser:
    NORMAL, SINGLE, DOUBLE = range(3)

    def __init__(self, text: str, variables: dict):
        self.text = text
        self.variables = variables

    def _walk(self, text: str):
        state = self.NORMAL
        escaped = False
        for ch in text:
            yield ch, escaped, state
            
            if escaped:
                escaped = False
            elif ch == config.operators.escape and state != self.SINGLE:
                escaped = True
            elif state == self.NORMAL:
                if ch == config.operators.quote: state = self.SINGLE
                elif ch == config.operators.double_quote: state = self.DOUBLE
            elif state == self.SINGLE and ch == config.operators.quote:
                state = self.NORMAL
            elif state == self.DOUBLE and ch == config.operators.double_quote:
                state = self.NORMAL
        
        if state != self.NORMAL:
            raise UnclosedQuoteError()

    def _split_by_pipe(self, text: str) -> list[str]:
        segments = []
        current = []
        
        for ch, escaped, state in self._walk(text):
            if not escaped and state == self.NORMAL and ch == config.operators.pipe:
                segments.append("".join(current))
                current = []
                continue
            current.append(ch)
            
        segments.append("".join(current))
        if text.strip().endswith(config.operators.pipe):
            raise ParseError("Empty command after pipe")
        return segments

    def _get_var_name(self, text: str, start: int) -> tuple[str, int]:
        if start >= len(text): return "", start
        if text[start] == config.operators.variable_start:
            end = text.find(config.operators.variable_end, start)
            if end == -1: return text[start+1:], len(text)
            return text[start+1:end], end + 1
        match = re.search(r'^(\w+)', text[start:])
        if match:
            name = match.group(1)
            return name, start + len(name)
        return "", start

    def _tokenize(self, text: str) -> list[str]:
        tokens = []
        current = []
        state = self.NORMAL
        escaped = False
        in_token = False
        
        i = 0
        while i < len(text):
            ch = text[i]
            
            if escaped:
                current.append(ch)
                escaped = False
                i += 1
                continue
            if ch == config.operators.escape and state != self.SINGLE:
                escaped = True
                in_token = True
                i += 1
                continue

            if state == self.NORMAL:
                if ch.isspace():
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False
                elif ch == config.operators.quote: 
                    state, in_token = self.SINGLE, True
                elif ch == config.operators.double_quote: 
                    state, in_token = self.DOUBLE, True
                elif ch == config.operators.variable:
                    name, next_i = self._get_var_name(text, i + 1)
                    current.append(str(self.variables.get(name, "")))
                    i, in_token = next_i - 1, True
                else:
                    current.append(ch)
                    in_token = True
            elif state == self.SINGLE:
                if ch == config.operators.quote: state = self.NORMAL
                else: current.append(ch)
            elif state == self.DOUBLE:
                if ch == config.operators.double_quote: state = self.NORMAL
                elif ch == config.operators.variable:
                    name, next_i = self._get_var_name(text, i + 1)
                    current.append(str(self.variables.get(name, "")))
                    i = next_i - 1
                else: current.append(ch)
            
            i += 1
            
        if in_token:
            tokens.append("".join(current))
        return tokens

    def parse(self) -> list[tuple[str, list[str]]]:
        segments = self._split_by_pipe(self.text)
        commands = []
        for segment in segments:
            toks = self._tokenize(segment)
            if toks:
                commands.append((toks[0], toks[1:]))
        
        if not commands: raise ParseError("Empty command")
        return commands