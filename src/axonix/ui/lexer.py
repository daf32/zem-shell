import os
import re
from typing import Callable, List, Tuple

from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer


class AxonixLexer(Lexer):
    """Syntax highlighter for Axonix shell commands."""
    
    # Regex patterns for special tokens
    NUMBER_PATTERN = re.compile(r'^-?\d+\.?\d*$')
    IP_PATTERN = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
    URL_PATTERN = re.compile(r'^https?://\S+$')
    
    def __init__(self, shell):
        self.shell = shell
        self.config = shell.config
        self._path_cache = {}  # Cache for path existence checks
        self._cache_size_limit = 100

    @property
    def system_commands(self) -> set:
        """Executables on the current PATH (cached per PATH value)."""
        from axonix.utils.executables import get_system_commands
        return set(get_system_commands())

    def invalidate_cache(self):
        """Drop every cache: PATH scan and path-existence results."""
        from axonix.utils.executables import refresh_system_commands
        refresh_system_commands()
        self._path_cache.clear()

    def clear_path_cache(self):
        """Forget path-existence results (called before each prompt so a
        file created by the previous command isn't still red)."""
        self._path_cache.clear()
    
    def _check_path_exists(self, path: str) -> bool:
        """Check if path exists with caching."""
        # Expand ~ to home directory
        expanded = os.path.expanduser(path)
        
        # Check cache first
        if expanded in self._path_cache:
            return self._path_cache[expanded]
        
        # Limit cache size
        if len(self._path_cache) >= self._cache_size_limit:
            # Clear half of cache (simple strategy)
            keys_to_remove = list(self._path_cache.keys())[:self._cache_size_limit // 2]
            for k in keys_to_remove:
                del self._path_cache[k]
        
        # Check existence
        exists = os.path.exists(expanded)
        self._path_cache[expanded] = exists
        return exists
    
    def _is_path_like(self, word: str) -> bool:
        """Check if word looks like a file path."""
        return (
            word.startswith("/") or 
            word.startswith("./") or 
            word.startswith("../") or
            word.startswith("~/") or
            ("/" in word and not word.startswith("-"))
        )
    
    def _classify_argument(self, word: str) -> str:
        """Classify an argument and return its style class."""
        # Check for flags/options
        if word.startswith("-"):
            return "class:flag"
        
        # Check for URLs
        if self.URL_PATTERN.match(word):
            return "class:url"
        
        # Check for IP addresses
        if self.IP_PATTERN.match(word):
            return "class:number"
        
        # Check for numbers
        if self.NUMBER_PATTERN.match(word):
            return "class:number"
        
        # Check for paths
        if self._is_path_like(word):
            if self._check_path_exists(word):
                return "class:path"
            else:
                return "class:path-notfound"
        
        # Default - no special styling
        return ""

    def lex_document(self, document: Document) -> Callable[[int], List[Tuple[str, str]]]:
        """Return a function that lexes a specific line."""
        
        def get_line(lineno: int) -> List[Tuple[str, str]]:
            if lineno >= len(document.lines):
                return []
                
            line = document.lines[lineno]
            tokens: List[Tuple[str, str]] = []
            
            i = 0
            is_first_word = True
            in_escape = False
            
            while i < len(line):
                char = line[i]
                
                # Handle escape character
                if in_escape:
                    tokens.append(("class:string", char))
                    in_escape = False
                    i += 1
                    continue
                
                if char == self.config.operators.escape:
                    tokens.append(("class:operator", char))
                    in_escape = True
                    i += 1
                    continue
                
                # Variable expansion ($VAR or ${VAR})
                if char == self.config.operators.variable:
                    tokens.append(("class:variable", char))
                    i += 1
                    
                    # Handle ${VAR} syntax
                    if i < len(line) and line[i] == self.config.operators.variable_start:
                        tokens.append(("class:variable", line[i]))
                        i += 1
                        var_name = ""
                        while i < len(line) and line[i] != self.config.operators.variable_end:
                            var_name += line[i]
                            i += 1
                        tokens.append(("class:variable", var_name))
                        if i < len(line):
                            tokens.append(("class:variable", line[i]))
                            i += 1
                    else:
                        # Regular $VAR syntax
                        var_name = ""
                        while i < len(line) and (line[i].isalnum() or line[i] in "_?"):
                            var_name += line[i]
                            i += 1
                        tokens.append(("class:variable", var_name))
                    continue
                
                # Pipe operator (| or ||)
                elif char == self.config.operators.pipe:
                    if i + 1 < len(line) and line[i+1] == self.config.operators.pipe:
                        tokens.append(("class:operator", "||"))
                        i += 2
                        is_first_word = True
                        continue
                    tokens.append(("class:operator", char))
                    is_first_word = True
                
                # Semicolon
                elif char == self.config.operators.semicolon:
                    tokens.append(("class:operator", char))
                    is_first_word = True
                
                # Ampersand (& or &&)
                elif char == "&":
                    if i + 1 < len(line) and line[i+1] == "&":
                        tokens.append(("class:operator", "&&"))
                        i += 2
                        is_first_word = True
                        continue
                    tokens.append(("class:operator", char))
                
                # Redirection operators
                elif char == self.config.operators.redirect_output:
                    if i + 1 < len(line) and line[i+1] == self.config.operators.redirect_output:
                        tokens.append(("class:operator", ">>"))
                        i += 2
                        continue
                    tokens.append(("class:operator", char))
                
                elif char == self.config.operators.redirect_input:
                    tokens.append(("class:operator", char))
                
                # Comment
                elif char == self.config.operators.comment:
                    tokens.append(("class:comment", line[i:]))
                    break
                
                # Quoted strings
                elif char in [self.config.operators.quote, self.config.operators.double_quote]:
                    quote_type = char
                    string_content = char
                    i += 1
                    
                    # Collect string until closing quote
                    while i < len(line):
                        c = line[i]
                        string_content += c
                        if c == quote_type:
                            break
                        # Handle escape in double quotes
                        if (
                            quote_type == self.config.operators.double_quote
                            and c == self.config.operators.escape
                        ):
                            if i + 1 < len(line):
                                i += 1
                                string_content += line[i]
                        i += 1
                    
                    tokens.append(("class:string", string_content))
                
                # Whitespace
                elif char.isspace():
                    tokens.append(("", char))
                
                # Words (commands, arguments)
                else:
                    word = ""
                    special_chars = [
                        self.config.operators.pipe, 
                        self.config.operators.redirect_output,
                        self.config.operators.redirect_input,
                        self.config.operators.comment,
                        self.config.operators.quote,
                        self.config.operators.double_quote,
                        self.config.operators.variable,
                        self.config.operators.semicolon,
                        "&",
                    ]
                    
                    while i < len(line) and not line[i].isspace() and line[i] not in special_chars:
                        word += line[i]
                        i += 1
                    
                    if is_first_word and word:
                        style_class = "class:command"
                        
                        # Validate command exists
                        is_builtin = word in self.shell.commands
                        is_alias = word in self.shell.context.aliases
                        
                        if not (is_builtin or is_alias):
                            # Check system commands (cached)
                            if word not in self.system_commands:
                                style_class = "class:error"
                            
                        tokens.append((style_class, word))
                        is_first_word = False
                    elif word:
                        # Classify the argument
                        style_class = self._classify_argument(word)
                        tokens.append((style_class, word))
                    continue
                
                i += 1
            
            return tokens

        return get_line
