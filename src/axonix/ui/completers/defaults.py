from axonix.ui.completers.base import BaseArgCompleter
from prompt_toolkit.completion import PathCompleter
from typing import Iterable, List
from prompt_toolkit.completion import Completion

class DirectoryCompleter(BaseArgCompleter):
    """Completes only directory paths."""
    
    def __init__(self):
        self._completer = PathCompleter(expanduser=True, only_directories=True)
    
    def get_completions(self, document, parts, word_before) -> Iterable[Completion]:
        # PathCompleter handles document internally well enough usually,
        # but we delegate directly
        from prompt_toolkit.completion import CompleteEvent
        # Creating a dummy event if needed, but None is usually fine for PathCompleter
        # However, checking if we need to reconstruct the document context
        return self._completer.get_completions(document, CompleteEvent(text_inserted=False, completion_requested=True))

class GitCompleter(BaseArgCompleter):
    """Simple git completer (hardcoded common commands for now)."""
    
    COMMANDS = [
        "status", "add", "commit", "push", "pull", "checkout", "branch", 
        "merge", "rebase", "log", "diff", "clone", "init", "remote", "fetch"
    ]
    
    def get_completions(self, document, parts, word_before) -> Iterable[Completion]:
        # parts[0] is 'git'
        # if len(parts) == 1, we are just after 'git ' (if space) or 'git' 
        
        # We need to detect if we are completing the subcommand (arg 1)
        # parts might be ['git', 'st'] -> len 2 -> completing subcommand
        
        if len(parts) == 2 and not word_before and text_has_space(document):
             # git [CURSOR]
             for cmd in self.COMMANDS:
                 yield Completion(cmd, start_position=0)
                 
        elif len(parts) == 2 and word_before:
             # git st[CURSOR]
             for cmd in self.COMMANDS:
                 if cmd.startswith(word_before):
                     yield Completion(cmd, start_position=-len(word_before))
                     
def text_has_space(document):
    return document.text_before_cursor.endswith(" ")
