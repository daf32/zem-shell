from typing import Iterable, List, Set

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from axonix.core.scan import NORMAL, scan
from axonix.ui.completers.defaults import (
    DockerCompleter,
    EnhancedPathCompleter,
    GitCompleter,
    NpmCompleter,
    PipCompleter,
    _current_word,
)
from axonix.ui.completers.registry import CompleterRegistry
from axonix.utils.executables import get_system_commands, refresh_system_commands


class AxonixCompleter(Completer):
    """Main completer for Axonix shell with context-aware completion."""

    #: Argument completers for common external tools.
    DEFAULT_COMPLETERS = {
        "git": GitCompleter,
        "pip": PipCompleter,
        "pip3": PipCompleter,
        "docker": DockerCompleter,
        "npm": NpmCompleter,
        "npx": NpmCompleter,
    }

    def __init__(self, shell):
        self.shell = shell
        self.path_completer = EnhancedPathCompleter(expanduser=True)
        self.registry = CompleterRegistry()
        self._register_default_completers()

    def _register_default_completers(self):
        """Register built-in completers, then the ones commands provide."""
        for name, factory in self.DEFAULT_COMPLETERS.items():
            self.registry.register(name, factory())

        # Builtins/plugins override the defaults for their own name.
        for name, cmd in self.shell.commands.items():
            completer = cmd.get_completer()
            if completer is not None:
                self.registry.register(name, completer)

    @property
    def system_commands(self) -> List[str]:
        """Executables on the current PATH (cached per PATH value)."""
        return get_system_commands()

    def invalidate_cache(self):
        """Drop the PATH scan cache (e.g. after installing new binaries)."""
        refresh_system_commands()

    def _find_command_start(self, text: str) -> int:
        """Index just after the last unquoted `|`, `||`, `;` or `&&`."""
        ops = self.shell.config.operators
        chars, _, _ = scan(text, ops)
        start = 0
        i = 0
        while i < len(chars):
            ch, escaped, state = chars[i]
            if not escaped and state == NORMAL:
                nxt = chars[i + 1] if i + 1 < len(chars) else None
                if ch == ops.pipe:
                    if nxt and nxt[0] == ops.pipe and not nxt[1] and nxt[2] == NORMAL:
                        i += 1
                    start = i + 1
                elif ch == ops.semicolon:
                    start = i + 1
                elif ch == "&" and nxt and nxt[0] == "&" and not nxt[1] and nxt[2] == NORMAL:
                    i += 1
                    start = i + 1
            i += 1
        return start

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """Get completions for the current input."""
        text_before = document.text_before_cursor

        cmd_start = self._find_command_start(text_before)
        current_segment = text_before[cmd_start:]
        stripped_segment = current_segment.lstrip()
        parts = stripped_segment.split()

        is_command_position = (
            not stripped_segment
            or (len(parts) == 1 and not current_segment[-1].isspace())
        )
        word_before = document.get_word_before_cursor()

        if is_command_position:
            # Use the whole first word: prompt_toolkit's "word" stops at
            # `-`, which would turn `docker-com` into a prefix of `com`.
            yield from self._complete_command_name(parts[0] if parts else "")
            return

        current_cmd_name = parts[0] if parts else ""
        resolved_cmd = current_cmd_name
        if current_cmd_name in self.shell.context.aliases:
            alias_parts = self.shell.context.aliases[current_cmd_name].split()
            if alias_parts:
                resolved_cmd = alias_parts[0]

        completer = self.registry.get(resolved_cmd)
        if completer is not None:
            produced = False
            for completion in completer.get_completions(document, parts, word_before):
                produced = True
                yield completion
            if produced or _current_word(text_before).startswith("-"):
                return
            # Nothing specific to offer: fall through to paths, so e.g.
            # `git add <TAB>` still completes files.

        yield from self.path_completer.get_completions(document, complete_event)

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
