from typing import TYPE_CHECKING
from src.commands.base import BaseCommand

if TYPE_CHECKING:
    from src.context import ExecutionContext

class EchoCommand(BaseCommand):
    help = "Print arguments"
    usage = "echo [text...]"

    def execute(self, args: list[str], context: 'ExecutionContext'):
        print(" ".join(args))