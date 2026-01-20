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
        """Split by pipe operator, but not || (logical OR)."""
        segments = []
        current = []
        
        chars = list(self._walk(text))
        i = 0
        while i < len(chars):
            ch, escaped, state = chars[i]
            
            if not escaped and state == self.NORMAL and ch == self.config.operators.pipe:
                # Check if this is part of || operator
                if i + 1 < len(chars):
                    next_ch, next_escaped, next_state = chars[i + 1]
                    if next_ch == "|" and not next_escaped and next_state == self.NORMAL:
                        # This is ||, not a pipe - add both chars and continue
                        current.append(ch)
                        current.append(next_ch)
                        i += 2
                        continue
                
                # This is a pipe operator
                segments.append("".join(current))
                current = []
                i += 1
                continue
            
            current.append(ch)
            i += 1
            
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
        if text[start] == "?":
            return "?", start + 1
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
                elif ch == self.config.operators.background:
                    # Background operator - should be at end of command
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False
                    tokens.append(self.config.operators.background)
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
        """Extract redirection and background information from tokens."""
        cmd_tokens = []
        stdin_file = None
        stdout_file = None
        append = False
        background = False
        
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
            elif token == self.config.operators.background:
                # Background operator should be at the end
                background = True
                i += 1
                continue
            cmd_tokens.append(token)
            i += 1
        return cmd_tokens, stdin_file, stdout_file, append, background

    def _split_logic(self, text: str) -> list[tuple[str, str]]:
        """Split text by logic operators (&&, ||, ;) into segments."""
        segments = []
        current = []
        
        i = 0
        chars = list(self._walk(text))
        while i < len(chars):
            ch, escaped, state = chars[i]
            
            if not escaped and state == self.NORMAL:
                # Check for && - must check next char is also & and not escaped
                if ch == "&" and i + 1 < len(chars):
                    next_ch, next_escaped, next_state = chars[i + 1]
                    if next_ch == "&" and not next_escaped and next_state == self.NORMAL:
                        segments.append(("".join(current), "&&"))
                        current = []
                        i += 2
                        continue
                    # Single & is background operator, handled in tokenize
                # Check for || - must check next char is also | and not escaped
                # But also need to avoid matching pipe operator |
                if ch == "|" and i + 1 < len(chars):
                    next_ch, next_escaped, next_state = chars[i + 1]
                    if next_ch == "|" and not next_escaped and next_state == self.NORMAL:
                        segments.append(("".join(current), "||"))
                        current = []
                        i += 2
                        continue
                # Check for ;
                if ch == self.config.operators.semicolon:
                    segments.append(("".join(current), ";"))
                    current = []
                    i += 1
                    continue
            
            current.append(ch)
            i += 1
            
        segments.append(("".join(current), None))
        return segments

    def parse(self) -> list[dict]:
        """
        Returns a list of logical units.
        Each unit is a dictionary:
        {
            "pipeline": list of commands,
            "logic": "&&" | "||" | ";" | None (operator to evaluate AFTER this pipeline)
        }
        """
        logic_segments = self._split_logic(self.text)
        units = []
        
        for segment_text, logic_op in logic_segments:
            if not segment_text.strip() and logic_op:
                if not units: continue # Leading separator
                raise ParseError(f"Empty command near {logic_op}")
            
            if not segment_text.strip():
                continue

            pipeline_segments = self._split_by_pipe(segment_text)
            commands = []
            for pipe_seg in pipeline_segments:
                toks = self._tokenize(pipe_seg)
                toks = self._expand_aliases(toks)
                if toks:
                    args, stdin, stdout, append, background = self._extract_redirections(toks)
                    if not args:
                        raise ParseError("Missing command name")
                    
                    # Background can only be on the last command in pipeline
                    is_last = len(commands) == len(pipeline_segments) - 1
                    
                    commands.append({
                        "name": args[0],
                        "args": args[1:],
                        "stdin_file": stdin,
                        "stdout_file": stdout,
                        "append": append,
                        "background": background and is_last  # Only last command can be background
                    })
            
            if commands:
                units.append({
                    "pipeline": commands,
                    "logic": logic_op
                })
        
        if not units: raise ParseError("Empty command")
        return units