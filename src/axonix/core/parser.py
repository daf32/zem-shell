import re
from typing import TYPE_CHECKING
from axonix.errors.parser_error import ParseError, UnclosedQuoteError

if TYPE_CHECKING:
    from axonix.config.settings import AppConfig

class Parser:
    NORMAL, SINGLE, DOUBLE = range(3)

    def __init__(self, text: str, variables: dict, aliases: dict, config: "AppConfig"):
        self.text = text
        self.variables = variables
        self.aliases = aliases
        self.config = config

    def _walk(self, text: str):
        state = self.NORMAL
        escaped = False
        for ch in text:
            yield ch, escaped, state
            
            if escaped:
                escaped = False
            elif ch == self.config.operators.escape and state != self.SINGLE:
                escaped = True
            elif state == self.NORMAL:
                if ch == self.config.operators.quote: state = self.SINGLE
                elif ch == self.config.operators.double_quote: state = self.DOUBLE
            elif state == self.SINGLE and ch == self.config.operators.quote:
                state = self.NORMAL
            elif state == self.DOUBLE and ch == self.config.operators.double_quote:
                state = self.NORMAL
        
        if state != self.NORMAL:
            raise UnclosedQuoteError()

    def _expand_aliases(self, tokens: list[str]) -> list[str]:
        if not tokens: 
            return tokens

        expanded_in_chain = set()

        current_tokens = tokens[:]

        while current_tokens[0] in self.aliases:
            alias_name = current_tokens[0]

            if alias_name in expanded_in_chain:
                break

            expanded_in_chain.add(alias_name)

            alias_value = self.aliases[alias_name]
            alias_tokens = self._tokenize(alias_value)

            if not alias_tokens:
                break

            current_tokens = alias_tokens + current_tokens[1:]

        return current_tokens

    def _split_by_pipe(self, text: str) -> list[str]:
        segments = []
        current = []
        
        for ch, escaped, state in self._walk(text):
            if not escaped and state == self.NORMAL and ch == self.config.operators.pipe:
                segments.append("".join(current))
                current = []
                continue
            current.append(ch)
            
        segments.append("".join(current))
        if text.strip().endswith(self.config.operators.pipe):
            raise ParseError("Empty command after pipe")
        return segments

    def _get_var_name(self, text: str, start: int) -> tuple[str, int]:
        if start >= len(text): return "", start
        if text[start] == self.config.operators.variable_start:
            end = text.find(self.config.operators.variable_end, start)
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
            if ch == self.config.operators.escape and state != self.SINGLE:
                escaped = True
                in_token = True
                i += 1
                continue

            if state == self.NORMAL:
                if ch.isspace():
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False
                elif ch == self.config.operators.quote: 
                    state, in_token = self.SINGLE, True
                elif ch == self.config.operators.double_quote: 
                    state, in_token = self.DOUBLE, True
                elif ch == self.config.operators.variable:
                    name, next_i = self._get_var_name(text, i + 1)
                    current.append(str(self.variables.get(name, "")))
                    i, in_token = next_i - 1, True
                elif ch in [self.config.operators.redirect_output, self.config.operators.redirect_input]:
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False
                    
                    # Handle multi-char operators (like >>)
                    can_match_append = (
                        ch == self.config.operators.redirect_output and 
                        self.config.operators.redirect_append.startswith(ch)
                    )
                    
                    if can_match_append:
                        rem = self.config.operators.redirect_append[1:]
                        if text[i+1:i+1+len(rem)] == rem:
                            tokens.append(self.config.operators.redirect_append)
                            i += len(rem)
                        else:
                            tokens.append(ch)
                    else:
                        tokens.append(ch)
                else:
                    current.append(ch)
                    in_token = True
            elif state == self.SINGLE:
                if ch == self.config.operators.quote: state = self.NORMAL
                else: current.append(ch)
            elif state == self.DOUBLE:
                if ch == self.config.operators.double_quote: state = self.NORMAL
                elif ch == self.config.operators.variable:
                    name, next_i = self._get_var_name(text, i + 1)
                    current.append(str(self.variables.get(name, "")))
                    i = next_i - 1
                else: current.append(ch)
            
            i += 1
            
        if in_token:
            tokens.append("".join(current))
        return tokens
    
    def _extract_redirections(self, tokens: list[str]):
        """Extract redirection information from tokens."""
        cmd_tokens = []
        stdin_file = None
        stdout_file = None
        append = False
        
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == self.config.operators.redirect_output or token == self.config.operators.redirect_append:
                if i + 1 < len(tokens):
                    stdout_file = tokens[i + 1]
                    append = (token == self.config.operators.redirect_append)
                    i += 2
                    continue
            elif token == self.config.operators.redirect_input:
                if i + 1 < len(tokens):
                    stdin_file = tokens[i + 1]
                    i += 2
                    continue
            cmd_tokens.append(token)
            i += 1
        return cmd_tokens, stdin_file, stdout_file, append

    def parse(self) -> list[dict]:
        segments = self._split_by_pipe(self.text)
        commands = []
        for segment in segments:
            toks = self._tokenize(segment)
            toks = self._expand_aliases(toks)
            if toks:
                args, stdin, stdout, append = self._extract_redirections(toks)
                if not args:
                    raise ParseError("Missing command name")
                
                commands.append({
                    "name": args[0],
                    "args": args[1:],
                    "stdin_file": stdin,
                    "stdout_file": stdout,
                    "append": append
                })
        
        if not commands: raise ParseError("Empty command")
        return commands