import os
from psh.builtins.base import BaseCommand
from psh.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psh.core.context import ExecutionContext


class CdCommand(BaseCommand):
    help = "Change the shell working directory"
    usage = "cd [directory]"

    def execute(self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None):
        target = args[0] if args else os.path.expanduser("~")
        
        try:
            os.chdir(target)
        except FileNotFoundError:
            raise ArgumentError(self.name, [target], reason="no such file or directory")
        except NotADirectoryError:
            raise ArgumentError(self.name, [target], reason="not a directory")
        except PermissionError:
            raise ArgumentError(self.name, [target], reason="permission denied")
        except Exception as e:
            raise ArgumentError(self.name, [target], reason=str(e))
