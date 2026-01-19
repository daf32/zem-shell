from prompt_toolkit.lexers import Lexer
from prompt_toolkit.document import Document
from typing import List, Tuple

class AxonixLexer(Lexer):
    def __init__(self, config):
        self.config = config

    def lex_document(self, document: Document):
        def get_line(lineno):
            line = document.lines[lineno]
            tokens = []
            
            i = 0
            is_first_word = True
            
            while i < len(line):
                char = line[i]
                
                # Keywords/Operators
                if char == self.config.operators.variable:
                    tokens.append(("class:variable", line[i]))
                    # Try to capture the variable name
                    i += 1
                    var_name = ""
                    while i < len(line) and (line[i].isalnum() or line[i] == "_"):
                        var_name += line[i]
                        i += 1
                    tokens.append(("class:variable", var_name))
                    continue
                elif char == self.config.operators.pipe:
                    tokens.append(("class:operator", char))
                    is_first_word = True # After pipe, next word is a command
                elif char in [self.config.operators.redirect_output, self.config.operators.redirect_input]:
                    # Check for >>
                    if char == self.config.operators.redirect_output and i + 1 < len(line) and line[i+1] == self.config.operators.redirect_output:
                        tokens.append(("class:operator", ">>"))
                        i += 2
                        continue
                    tokens.append(("class:operator", char))
                elif char == self.config.operators.comment:
                    tokens.append(("class:comment", line[i:]))
                    break
                elif char in [self.config.operators.quote, self.config.operators.double_quote]:
                    tokens.append(("class:string", char))
                    quote_type = char
                    i += 1
                    str_val = ""
                    while i < len(line) and line[i] != quote_type:
                        str_val += line[i]
                        i += 1
                    tokens.append(("class:string", str_val))
                    if i < len(line):
                        tokens.append(("class:string", line[i]))
                elif char.isspace():
                    tokens.append(("", char))
                else:
                    # Capture word
                    word = ""
                    while i < len(line) and not line[i].isspace() and line[i] not in [
                        self.config.operators.pipe, 
                        self.config.operators.redirect_output,
                        self.config.operators.redirect_input,
                        self.config.operators.comment,
                        self.config.operators.quote,
                        self.config.operators.double_quote,
                        self.config.operators.variable
                    ]:
                        word += line[i]
                        i += 1
                    
                    if is_first_word:
                        tokens.append(("class:command", word))
                        is_first_word = False
                    else:
                        tokens.append(("", word))
                    continue
                
                i += 1
            return tokens

        return get_line
