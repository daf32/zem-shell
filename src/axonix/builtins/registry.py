"""Command registry for managing builtin commands."""
from typing import Dict, Optional
from axonix.builtins.base import BaseCommand


class CommandRegistry:
    """Registry for builtin commands."""
    
    _instance: Optional['CommandRegistry'] = None
    _commands: Dict[str, BaseCommand] = {}
    _command_classes: Dict[str, type[BaseCommand]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, command_class: type[BaseCommand]) -> None:
        """Register a command class."""
        if not issubclass(command_class, BaseCommand):
            raise TypeError(f"{command_class} is not a subclass of BaseCommand")
        
        # Create instance to get name
        instance = command_class()
        name = instance.name
        
        if not name:
            raise ValueError(f"Command class {command_class} has no name")
        
        if name in cls._command_classes:
            raise ValueError(f"Command '{name}' is already registered")
        
        cls._command_classes[name] = command_class
    
    @classmethod
    def get_command(cls, name: str) -> Optional[BaseCommand]:
        """Get a command instance by name."""
        if name not in cls._command_classes:
            return None
        
        # Lazy instantiation - create instance when needed
        if name not in cls._commands:
            cls._commands[name] = cls._command_classes[name]()
        
        return cls._commands[name]
    
    @classmethod
    def get_all_commands(cls) -> Dict[str, BaseCommand]:
        """Get all registered commands."""
        # Ensure all commands are instantiated
        for name in cls._command_classes:
            if name not in cls._commands:
                cls._commands[name] = cls._command_classes[name]()
        
        return cls._commands.copy()
    
    @classmethod
    def get_command_names(cls) -> list[str]:
        """Get all registered command names."""
        return list(cls._command_classes.keys())
    
    @classmethod
    def clear(cls):
        """Clear the registry (useful for testing)."""
        cls._commands.clear()
        cls._command_classes.clear()
