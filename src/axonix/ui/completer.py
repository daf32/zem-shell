from prompt_toolkit.completion import Completer, Completion, PathCompleter
from typing import Iterable, List, Optional
import os
from axonix.utils.executables import get_system_commands
from axonix.ui.completers.registry import CompleterRegistry
from axonix.ui.completers.defaults import GitCompleter, DirectoryCompleter
from axonix.ui.completers.theme import ThemeCompleter

class AxonixCompleter(Completer):
    def __init__(self, shell):
        self.shell = shell
        self.path_completer = PathCompleter(expanduser=True)
        self._system_commands = None
        
        # Register default completers
        # TODO: Move this registration to a better place (maybe app startup)
        CompleterRegistry.register("git", GitCompleter())
        CompleterRegistry.register("cd", DirectoryCompleter())
        CompleterRegistry.register("theme", ThemeCompleter(self.shell.config))
        
        # We can also register alias resolution later

    @property
    def system_commands(self):
        if self._system_commands is None:
            self._system_commands = get_system_commands()
        return self._system_commands

    def get_completions(self, document, complete_event) -> Iterable[Completion]:
        text_before = document.text_before_cursor
        
        # 1. Identify context (command vs args)
        # Find the start of the current command segment
        last_separator_idx = -1
        # Simple parser for pipes/semicolons
        for i, char in enumerate(text_before):
            if char in (self.shell.config.operators.pipe, self.shell.config.operators.semicolon):
                if i == 0 or text_before[i-1] != self.shell.config.operators.escape:
                    last_separator_idx = i
        
        current_segment = text_before[last_separator_idx + 1:]
        stripped_segment = current_segment.lstrip()
        
        # 2. Parse segment into parts
        parts = stripped_segment.split()
        
        # Determine if we are typing the command name itself
        # Logic: if no space in segment (and doesn't look like a path starting), it's a command
        # BUT: typing "git " -> parts=['git'], we are past command
        # typing "git" -> parts=['git'], we are ON command if no trailing space
        
        is_command_position = False
        if not stripped_segment:
             # Empty input
            is_command_position = True
        elif len(parts) == 1 and not current_segment.endswith(" "):
            # Typing the first word
            is_command_position = True

        word_before = document.get_word_before_cursor()

        # 3. Handle Command Name Completion
        if is_command_position:
            builtin_cmds = list(self.shell.commands.keys())
            aliases = list(self.shell.context.aliases.keys())
            system_cmds = self.system_commands
            
            all_alternatives = sorted(set(builtin_cmds + aliases + system_cmds))
            
            for word in all_alternatives:
                if word.startswith(word_before):
                    yield Completion(word, start_position=-len(word_before))
            return

        # 4. Handle Argument Completion
        # Get the command name
        current_cmd_name = parts[0] if parts else ""
        
        # Delegate to registered completer
        completer = CompleterRegistry.get(current_cmd_name)
        if completer:
            for completion in completer.get_completions(document, parts, word_before):
                yield completion
            return

        # Fallback: Path completion
        # If we are not typing a command, and no specific completer handled it, use path completion
        if not is_command_position:
            for completion in self.path_completer.get_completions(document, complete_event):
                yield completion
