import inspect
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class BaseCommand:
    name: str = ""
    help: str = ""
    usage: str = ""
    tags: list[str] = ["builtin"]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        file = inspect.getfile(cls)
        cls.name = Path(file).stem
        
        # Auto-register command
        from axonix.builtins.registry import CommandRegistry
        CommandRegistry.register(cls)

    def execute(self, args: list[str], context: "ExecutionContext", 
            stdin=sys.stdin, stdout=sys.stdout) -> None:
        raise NotImplementedError
    