from typing import Iterable, List, Optional, Set

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from axonix.ui.completers.defaults import (
    DirectoryCompleter,
    DockerCompleter,
    EnhancedPathCompleter,
    GitCompleter,
    NpmCompleter,
    PipCompleter,
)
from axonix.ui.completers.registry import CompleterRegistry
from axonix.ui.completers.theme import ThemeCompleter
from axonix.utils.executables import get_system_commands


class AxonixCompleter(Completer):
    """Main completer for Axonix shell with context-aware completion."""
    
    def __init__(self, shell):
        self.shell = shell
        self.path_completer = EnhancedPathCompleter(expanduser=True)
        self._system_commands: Optional[List[str]] = None
        self._registered = False
        
        # Register default completers
        self._register_default_completers()

    def _register_default_completers(self):
        """Register built-in completers for common commands."""
        if self._registered:
            return
        
        # Core shell completers
        CompleterRegistry.register("git", GitCompleter())
        CompleterRegistry.register("cd", DirectoryCompleter())
        CompleterRegistry.register("theme", ThemeCompleter(self.shell.config))
        
        # Package manager completers
        CompleterRegistry.register("pip", PipCompleter())
        CompleterRegistry.register("pip3", PipCompleter())
        CompleterRegistry.register("docker", DockerCompleter())
        CompleterRegistry.register("npm", NpmCompleter())
        CompleterRegistry.register("npx", NpmCompleter())
        CompleterRegistry.register("yarn", NpmCompleter())  # Similar commands
        CompleterRegistry.register("pnpm", NpmCompleter())  # Similar commands
        
        # Also register completers from commands that provide them
        for name, cmd in self.shell.commands.items():
            completer = cmd.get_completer()
            if completer is not None:
                CompleterRegistry.register(name, completer)
        
        self._registered = True

    @property
    def system_commands(self) -> List[str]:
        """Get system commands (cached)."""
        if self._system_commands is None:
            self._system_commands = get_system_commands()
        return self._system_commands
    
    def invalidate_cache(self):
        """Invalidate the system commands cache."""
        self._system_commands = None

    def _find_command_start(self, text: str) -> int:
        """Find the start of the current command in the text.
        
        Returns the index after the last unescaped separator (|, ;, &&, ||).
        """
        last_separator_idx = -1
        i = 0
        ops = self.shell.config.operators
        
        while i < len(text):
            char = text[i]
            
            # Skip escaped characters
            if i > 0 and text[i-1] == ops.escape:
                i += 1
                continue
            
            # Check for multi-char operators first
            if char == '&' and i + 1 < len(text) and text[i+1] == '&':
                last_separator_idx = i + 1
                i += 2
                continue
            
            if char == ops.pipe:
                if i + 1 < len(text) and text[i+1] == ops.pipe:
                    last_separator_idx = i + 1
                    i += 2
                    continue
                last_separator_idx = i
            
            elif char == ops.semicolon:
                last_separator_idx = i
            
            i += 1
        
        return last_separator_idx + 1

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """Get completions for the current input."""
        text_before = document.text_before_cursor
        
        # Find the start of the current command segment
        cmd_start = self._find_command_start(text_before)
        current_segment = text_before[cmd_start:]
        stripped_segment = current_segment.lstrip()
        
        # Parse segment into parts (simple split for now)
        parts = stripped_segment.split()
        
        # Determine if we are typing the command name itself
        is_command_position = False
        if not stripped_segment:
            # Empty input or just whitespace
            is_command_position = True
        elif len(parts) == 1 and not current_segment.endswith(" "):
            # Typing the first word
            is_command_position = True

        word_before = document.get_word_before_cursor()

        # Handle Command Name Completion
        if is_command_position:
            yield from self._complete_command_name(word_before)
            return

        # Handle Argument Completion
        current_cmd_name = parts[0] if parts else ""
        
        # Check if command has an alias and resolve it
        resolved_cmd = current_cmd_name
        if current_cmd_name in self.shell.context.aliases:
            alias_value = self.shell.context.aliases[current_cmd_name]
            # Get first word of alias expansion
            alias_parts = alias_value.split()
            if alias_parts:
                resolved_cmd = alias_parts[0]
        
        # Try registered completer
        completer = CompleterRegistry.get(resolved_cmd)
        if completer:
            for completion in completer.get_completions(document, parts, word_before):
                yield completion
            return

        # Fallback: Path completion
        for completion in self.path_completer.get_completions(document, complete_event):
            yield completion
    
    def _complete_command_name(self, prefix: str) -> Iterable[Completion]:
        """Complete command names (builtins, aliases, system commands)."""
        seen: Set[str] = set()
        
        # Builtin commands (highest priority)
        for cmd in sorted(self.shell.commands.keys()):
            if cmd.startswith(prefix) and cmd not in seen:
                seen.add(cmd)
                yield Completion(
                    cmd, 
                    start_position=-len(prefix),
                    display_meta="builtin"
                )
        
        # Aliases
        for alias in sorted(self.shell.context.aliases.keys()):
            if alias.startswith(prefix) and alias not in seen:
                seen.add(alias)
                alias_value = self.shell.context.aliases[alias]
                # Truncate long alias values for display
                display_value = alias_value if len(alias_value) <= 30 else alias_value[:27] + "..."
                yield Completion(
                    alias, 
                    start_position=-len(prefix),
                    display_meta=f"alias → {display_value}"
                )
        
        # System commands
        for cmd in sorted(self.system_commands):
            if cmd.startswith(prefix) and cmd not in seen:
                seen.add(cmd)
                yield Completion(
                    cmd, 
                    start_position=-len(prefix)
                )
