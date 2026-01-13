from typing import TYPE_CHECKING, List
import inspect
from pathlib import Path

if TYPE_CHECKING:
    from src.context import ExecutionContext

class BaseCommand:
    name: str = ""
    help: str = ""
    usage: str = ""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        file = inspect.getfile(cls)
        cls.name = Path(file).stem

    def execute(self, args: List[str], context: 'ExecutionContext') -> None:
        raise NotImplementedError
    