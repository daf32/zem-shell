import os
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
                if ch == self.config.operators.quote:
                    state = self.SINGLE
                elif ch == self.config.operators.double_quote:
                    state = self.DOUBLE
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
            
            # Check for parameters ($1, $2, etc.)
            params = re.findall(r'\$(\d+)', alias_value)
            
            if params:
                # Parameterized alias
                indices = [int(p) for p in params]
                max_index = max(indices) if indices else 0
                
                # Arguments available after the command name
                available_args = current_tokens[1:]
                
                # Consume arguments needed by alias
                consumed_args = []
                for i in range(max_index):
                    if i < len(available_args):
                        consumed_args.append(available_args[i])
                    else:
                        consumed_args.append("") # Missing arg becomes empty
                
                remaining_args = available_args[max_index:]
                
                # Perform substitution in the raw string value
                new_value = alias_value
                for i in range(1, max_index + 1):
                    val = consumed_args[i-1]
                    # Simple replacement of $N
                    # Note: this might replace inside strings if not careful, but alias definitions
                    # are treated as raw text templates here.
                    new_value = new_value.replace(f"${i}", val)
                
                alias_tokens = self._tokenize(new_value)
                current_tokens = alias_tokens + remaining_args
            else:
                # Simple alias
                alias_tokens = self._tokenize(alias_value)
                current_tokens = alias_tokens + current_tokens[1:]

            if not current_tokens:
                break

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
        if start >= len(text):
            return "", start
        if text[start] == self.config.operators.variable_start:
            end = text.find(self.config.operators.variable_end, start)
            if end == -1:
                return text[start+1:], len(text)
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
                # Keep the backslash: quotes stay in the token until
                # `_remove_quotes`, which must see the escape to know this
                # character is literal (otherwise `a\'b` would read as a
                # quote opening).
                current.append(self.config.operators.escape)
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
                    current.append(ch)
                elif ch == self.config.operators.double_quote: 
                    state, in_token = self.DOUBLE, True
                    current.append(ch)
                elif ch == self.config.operators.variable:
                    name, next_i = self._get_var_name(text, i + 1)
                    current.append(str(self.variables.get(name, "")))
                    i, in_token = next_i - 1, True
                elif ch in (
                    self.config.operators.redirect_output,
                    self.config.operators.redirect_input,
                ):
                    # `2>` / `1>`: a bare fd number glued to `>` is an fd
                    # prefix (bash: `echo 2>x` redirects, `echo 2 >x` prints).
                    fd_prefix = ""
                    if (
                        ch == self.config.operators.redirect_output
                        and in_token
                        and "".join(current) in ("1", "2")
                    ):
                        fd_prefix = "".join(current)
                        current, in_token = [], False
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False

                    op = ch
                    if ch == self.config.operators.redirect_output:
                        rem = self.config.operators.redirect_append[1:]
                        if text[i + 1:i + 1 + len(rem)] == rem:
                            op = self.config.operators.redirect_append
                            i += len(rem)
                        elif fd_prefix == "2" and text[i + 1:i + 3] == "&1":
                            op = "2>&1"
                            i += 2
                            fd_prefix = ""
                    if fd_prefix == "2":
                        op = "2" + op
                    tokens.append(op)
                elif ch == self.config.operators.background:
                    if in_token:
                        tokens.append("".join(current))
                        current, in_token = [], False
                    # `&>` / `&>>`: redirect both stdout and stderr.
                    if text[i + 1:i + 2] == self.config.operators.redirect_output:
                        if text[i + 1:i + 3] == self.config.operators.redirect_append:
                            tokens.append("&>>")
                            i += 2
                        else:
                            tokens.append("&>")
                            i += 1
                    else:
                        # Background operator - should be at end of command
                        tokens.append(self.config.operators.background)
                else:
                    current.append(ch)
                    in_token = True
            elif state == self.SINGLE:
                if ch == self.config.operators.quote: 
                    state = self.NORMAL
                    current.append(ch)
                else:
                    current.append(ch)
            elif state == self.DOUBLE:
                if ch == self.config.operators.double_quote: 
                    state = self.NORMAL
                    current.append(ch)
                elif ch == self.config.operators.variable:
                    name, next_i = self._get_var_name(text, i + 1)
                    current.append(str(self.variables.get(name, "")))
                    i = next_i - 1
                else:
                    current.append(ch)
            
            i += 1
            
        if in_token:
            tokens.append("".join(current))
        return tokens
    
    def _extract_redirections(self, tokens: list[str]) -> tuple[list[str], dict]:
        """Split tokens into command words and a redirection spec.

        The spec has keys ``stdin_file``, ``stdout_file``, ``append``,
        ``stderr_file``, ``stderr_append``, ``stderr_to_stdout`` and
        ``background``.
        """
        out = self.config.operators.redirect_output
        app = self.config.operators.redirect_append
        cmd_tokens: list[str] = []
        spec: dict = {
            "stdin_file": None,
            "stdout_file": None,
            "append": False,
            "stderr_file": None,
            "stderr_append": False,
            "stderr_to_stdout": False,
            "background": False,
        }

        def target(i: int, op: str) -> str:
            if i + 1 >= len(tokens):
                raise ParseError(f"Missing target after '{op}'")
            return tokens[i + 1]

        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in (out, app):
                spec["stdout_file"] = target(i, token)
                spec["append"] = token == app
                i += 2
            elif token in ("2" + out, "2" + app):
                spec["stderr_file"] = target(i, token)
                spec["stderr_append"] = token == "2" + app
                i += 2
            elif token in ("&>", "&>>"):
                spec["stdout_file"] = target(i, token)
                spec["append"] = token == "&>>"
                spec["stderr_to_stdout"] = True
                i += 2
            elif token == "2>&1":
                spec["stderr_to_stdout"] = True
                i += 1
            elif token == self.config.operators.redirect_input:
                spec["stdin_file"] = target(i, token)
                i += 2
            elif token == self.config.operators.background:
                spec["background"] = True
                i += 1
            else:
                cmd_tokens.append(token)
                i += 1
        return cmd_tokens, spec

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

    def _remove_quotes(self, text: str) -> str:
        """Remove quotes from text."""
        if not text:
            return text
        
        result = []
        state = self.NORMAL
        escaped = False
        
        for ch in text:
            if escaped:
                result.append(ch)
                escaped = False
                continue
            
            if ch == self.config.operators.escape and state != self.SINGLE:
                escaped = True
                continue
            
            if state == self.NORMAL:
                if ch == self.config.operators.quote:
                    state = self.SINGLE
                elif ch == self.config.operators.double_quote:
                    state = self.DOUBLE
                else:
                    result.append(ch)
            elif state == self.SINGLE:
                if ch == self.config.operators.quote:
                    state = self.NORMAL
                else:
                    result.append(ch)
            elif state == self.DOUBLE:
                if ch == self.config.operators.double_quote:
                    state = self.NORMAL
                else:
                    result.append(ch)
                
        return "".join(result)

    def _expand_tilde(self, token: str) -> str | None:
        """Expand a leading unquoted ``~`` / ``~user`` in a raw token.

        Returns the expanded (and unquoted) word, or ``None`` if the token
        doesn't start with a tilde. Only the prefix up to the first ``/``
        is expanded; the rest of the word is unquoted as usual.
        """
        if not token.startswith("~"):
            return None
        head, sep, rest = token.partition("/")
        expanded = os.path.expanduser(head)
        if expanded == head:  # unknown user: leave the word alone
            return None
        return expanded + sep + self._remove_quotes(rest)

    def _expand_word(self, token: str) -> str:
        """Unquote a single word, expanding a leading tilde."""
        return self._expand_tilde(token) or self._remove_quotes(token)

    def _expand_words(self, tokens: list[str]) -> list[str]:
        """Unquote words, expanding tildes and globs."""
        import glob

        expanded_tokens = []

        for token in tokens:
            tilde = self._expand_tilde(token)
            if tilde is not None:
                token, remove = tilde, False
            else:
                remove = True
            # Check if token contains unquoted wildcards
            # We need to scan the token similar to _tokenize or _remove_quotes
            # but detecting if *?[ are unquoted
            
            has_glob = False
            state = self.NORMAL
            escaped = False
            
            # Simple heuristic first: if no globs chars, skip expensive parse
            if not any(c in token for c in "*?[]"):
                expanded_tokens.append(self._remove_quotes(token) if remove else token)
                continue
            
            # Verify if wildcards are unquoted
            for ch in token:
                if escaped:
                    escaped = False
                    continue
                if ch == self.config.operators.escape and state != self.SINGLE:
                    escaped = True
                    continue
                
                if state == self.NORMAL:
                    if ch == self.config.operators.quote:
                        state = self.SINGLE
                    elif ch == self.config.operators.double_quote:
                        state = self.DOUBLE
                    elif ch in "*?[]":
                        has_glob = True
                        break
                elif state == self.SINGLE:
                    if ch == self.config.operators.quote:
                        state = self.NORMAL
                elif state == self.DOUBLE:
                    if ch == self.config.operators.double_quote:
                        state = self.NORMAL
            
            if has_glob:
                pattern = self._remove_quotes(token) if remove else token
                matches = glob.glob(pattern)
                expanded_tokens.extend(sorted(matches) if matches else [pattern])
            else:
                expanded_tokens.append(self._remove_quotes(token) if remove else token)

        return expanded_tokens

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
                if not units:
                    continue
                raise ParseError(f"Empty command near {logic_op}")
            
            if not segment_text.strip():
                continue

            pipeline_segments = self._split_by_pipe(segment_text)
            commands = []
            for pipe_seg in pipeline_segments:
                toks = self._tokenize(pipe_seg)
                toks = self._expand_aliases(toks)
                if toks:
                    args_raw, spec = self._extract_redirections(toks)

                    if not args_raw:
                        raise ParseError("Missing command name")

                    final_args = self._expand_words(args_raw)
                    for key in ("stdin_file", "stdout_file", "stderr_file"):
                        if spec[key]:
                            spec[key] = self._expand_word(spec[key])

                    is_last = len(commands) == len(pipeline_segments) - 1
                    spec["background"] = spec["background"] and is_last

                    commands.append({"name": final_args[0], "args": final_args[1:], **spec})
            
            if commands:
                units.append({
                    "pipeline": commands,
                    "logic": logic_op
                })
        
        if not units:
            raise ParseError("Empty command")
        return units