from axonix.ui.completers.base import BaseArgCompleter
from prompt_toolkit.completion import Completion, PathCompleter, CompleteEvent
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
                self._cached_themes = sorted(manager.list_themes().keys())
            except Exception:
                self._cached_themes = []
        return self._cached_themes
    
    def invalidate_cache(self):
        """Invalidate the theme cache (call after theme import/install)."""
        self._cached_themes = None

    def get_completions(self, document: Document, parts: List[str], word_before: str) -> Iterable[Completion]:
        """Complete theme command arguments.
        
        Args:
            document: The document being edited
            parts: Command parts (e.g., ['theme', 'set'])
            word_before: The word currently being typed
        """
        # parts[0] is 'theme'
        arg_count = len(parts) - 1
        ends_with_space = document.text_before_cursor.endswith(" ")
        
        # 1. Complete Subcommand (arg 1)
        if arg_count == 0 and ends_with_space:
            # 'theme ' - show all subcommands
            for subcmd in sorted(self.SUBCOMMANDS):
                yield Completion(subcmd, start_position=0)
        elif arg_count == 1 and word_before and not ends_with_space:
            # 'theme s' - filter subcommands by prefix
            for subcmd in sorted(self.SUBCOMMANDS):
                if subcmd.startswith(word_before):
                    yield Completion(subcmd, start_position=-len(word_before))
        
        # 2. Complete Arguments for Subcommand (arg 2+)
        elif arg_count >= 1:
            subcommand = parts[1].lower() if len(parts) > 1 else ""
            
            # theme set/preview/variants <NAME>
            if subcommand in ("set", "preview", "variants"):
                if arg_count == 1 and ends_with_space:
                    # 'theme set ' - show all themes
                    for theme in self.theme_names:
                        yield Completion(theme, start_position=0)
                elif arg_count == 2 and word_before and not ends_with_space:
                    # 'theme set dr' - filter by prefix
                    for theme in self.theme_names:
                        if theme.startswith(word_before):
                            yield Completion(theme, start_position=-len(word_before))
            
            # theme import <PATH>
            elif subcommand == "import":
                complete_event = CompleteEvent(text_inserted=False, completion_requested=True)
                for completion in self.path_completer.get_completions(document, complete_event):
                    yield completion
