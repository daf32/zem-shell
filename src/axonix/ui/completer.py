from prompt_toolkit.completion import Completer, Completion, PathCompleter
from typing import Iterable, List, Optional
import os
from axonix.utils.executables import get_system_commands

class AxonixCompleter(Completer):
    def __init__(self, shell):
        self.shell = shell
        self.path_completer = PathCompleter(expanduser=True)
        self.dir_completer = PathCompleter(expanduser=True, only_directories=True)
        self._system_commands = None
        self._cached_themes = None
        
        # Commands that only accept directories
        self.dir_only_commands = {"cd"}
        
        # Theme subcommands
        self.theme_subcommands = ["list", "set", "preview", "export", "import", "install", "variants"]

    @property
    def system_commands(self):
        if self._system_commands is None:
            self._system_commands = get_system_commands()
        return self._system_commands
    
    @property
    def theme_names(self) -> List[str]:
        """Get available theme names."""
        if self._cached_themes is None:
            try:
                from axonix.utils.themes import ThemeManager
                manager = ThemeManager(self.shell.config)
                self._cached_themes = list(manager.list_themes().keys())
            except Exception:
                self._cached_themes = []
        return self._cached_themes

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text_before = document.text_before_cursor
        
        # Find the start of the current command segment (after last pipe or semicolon)
        last_separator_idx = -1
        for i, char in enumerate(text_before):
            if char in (self.shell.config.operators.pipe, self.shell.config.operators.semicolon):
                if i == 0 or text_before[i-1] != self.shell.config.operators.escape:
                    last_separator_idx = i
        
        current_segment = text_before[last_separator_idx + 1:]
        stripped_segment = current_segment.lstrip()
        
        # Parse current segment to understand context
        parts = stripped_segment.split()
        current_cmd = parts[0] if parts else ""
        arg_count = len(parts) - 1 if parts else 0
        
        # Get the word currently being typed
        word_before = document.get_word_before_cursor()
        
        # Determine if we're completing a command name
        is_command_position = " " not in stripped_segment and not stripped_segment.startswith((".", "/"))
        
        if is_command_position:
            # Command/Alias/System Command completion
            builtin_cmds = list(self.shell.commands.keys())
            aliases = list(self.shell.context.aliases.keys())
            system_cmds = self.system_commands
            
            all_alternatives = sorted(set(builtin_cmds + aliases + system_cmds))
            
            for word in all_alternatives:
                if word.startswith(word_before):
                    yield Completion(word, start_position=-len(word_before))
            return
        
        # Context-aware completions based on command
        if current_cmd == "theme":
            # Theme command completions
            for completion in self._complete_theme(parts, word_before):
                yield completion
            return
        
        if current_cmd in self.dir_only_commands:
            # Directory-only completion for cd
            for completion in self.dir_completer.get_completions(document, complete_event):
                yield completion
            return
        
        # Default: path completion for arguments
        if " " in stripped_segment or stripped_segment.startswith((".", "/")):
            for completion in self.path_completer.get_completions(document, complete_event):
                yield completion
    
    def _complete_theme(self, parts: List[str], word_before: str) -> Iterable[Completion]:
        """Complete theme command arguments."""
        arg_count = len(parts) - 1
        
        if arg_count == 0 or (arg_count == 1 and word_before):
            # Complete subcommand
            for subcmd in self.theme_subcommands:
                if subcmd.startswith(word_before):
                    yield Completion(subcmd, start_position=-len(word_before))
        
        elif arg_count >= 1:
            subcommand = parts[1] if len(parts) > 1 else ""
            
            if subcommand in ("set", "preview", "variants"):
                # Complete theme name
                for theme in self.theme_names:
                    if theme.startswith(word_before):
                        yield Completion(theme, start_position=-len(word_before))
            
            elif subcommand == "import":
                # Path completion for import
                from prompt_toolkit.document import Document
                for completion in self.path_completer.get_completions(
                    Document(word_before, len(word_before)), None
                ):
                    yield completion
