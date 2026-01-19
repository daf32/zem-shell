from prompt_toolkit.completion import Completer, Completion, PathCompleter
from typing import Iterable

class AxonixCompleter(Completer):
    def __init__(self, shell):
        self.shell = shell
        self.path_completer = PathCompleter(expanduser=True)

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text = document.text_before_cursor.lstrip()
        
        # If we are completing the first word, it's a command or alias
        if " " not in text:
            # Command/Alias completion
            commands = list(self.shell.commands.keys())
            aliases = list(self.shell.context.aliases.keys())
            
            for word in sorted(set(commands + aliases)):
                if word.startswith(text):
                    yield Completion(word, start_position=-len(text))
        else:
            # Path completion
            for completion in self.path_completer.get_completions(document, complete_event):
                yield completion
