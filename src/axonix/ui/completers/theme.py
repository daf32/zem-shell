from axonix.ui.completers.base import BaseArgCompleter
from prompt_toolkit.completion import Completion, PathCompleter
from prompt_toolkit.document import Document
from typing import Iterable, List

class ThemeCompleter(BaseArgCompleter):
    """Completer for 'theme' command."""
    
    SUBCOMMANDS = ["list", "set", "preview", "export", "import", "install", "variants"]
    
    def __init__(self, shell_config):
        self.config = shell_config
        self.path_completer = PathCompleter(expanduser=True)
        self._cached_themes = None

    @property
    def theme_names(self) -> List[str]:
        """Get available theme names (cached lazy load)."""
        if self._cached_themes is None:
            try:
                from axonix.utils.themes import ThemeManager
                manager = ThemeManager(self.config)
                self._cached_themes = list(manager.list_themes().keys())
            except Exception:
                self._cached_themes = []
        return self._cached_themes

    def get_completions(self, document: Document, parts: List[str], word_before: str) -> Iterable[Completion]:
        # parts[0] is 'theme'
        arg_count = len(parts) - 1
        
        # 1. Complete Subcommand (arg 1)
        if arg_count == 0 or (arg_count == 1 and word_before):
             # theme [CURSOR] or theme s[CURSOR]
            for subcmd in self.SUBCOMMANDS:
                if subcmd.startswith(word_before):
                    yield Completion(subcmd, start_position=-len(word_before))
        
        # 2. Complete Arguments for Subcommand (arg 2)
        elif arg_count >= 1:
            subcommand = parts[1]
            
            # theme set <NAME>
            if subcommand in ("set", "preview", "variants"):
                if arg_count == 1: # Just finished typing subcommand
                     if document.text_before_cursor.endswith(" "):
                        for theme in self.theme_names:
                             yield Completion(theme, start_position=0)
                elif arg_count == 2: # Typing theme name
                     for theme in self.theme_names:
                        if theme.startswith(word_before):
                            yield Completion(theme, start_position=-len(word_before))
            
            # theme import <PATH>
            elif subcommand == "import":
                # Delegate to PathCompleter
                 # We need to construct a fake document for PathCompleter normally, 
                 # or just pass the current state
                 for completion in self.path_completer.get_completions(document, None):
                     yield completion
