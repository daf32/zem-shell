from typing import Dict, Type
from axonix.ui.completers.base import BaseArgCompleter

class CompleterRegistry:
    """Registry for command argument completers."""
    
    _completers: Dict[str, BaseArgCompleter] = {}

    @classmethod
    def register(cls, command_name: str, completer: BaseArgCompleter):
        """Register a completer for a specific command."""
        cls._completers[command_name] = completer

    @classmethod
    def get(cls, command_name: str) -> BaseArgCompleter | None:
        """Get completer for a command."""
        return cls._completers.get(command_name)
    
    @classmethod
    def get_all(cls) -> Dict[str, BaseArgCompleter]:
        return cls._completers
