import os
from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class CdCommand(BaseCommand):
    help = "Change the shell working directory"
    usage = "cd [directory | - | ~]"
    tags = ["builtin"]
    examples = [
        "cd            - Go to home directory",
        "cd /path/to   - Go to specified path",
        "cd -          - Go to previous directory",
        "cd ~          - Go to home directory",
        "cd ..         - Go to parent directory",
    ]

    def execute(self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None):
        # Store current directory before changing
        old_pwd = os.getcwd()
        
        # Determine target directory
        if not args:
            target = os.path.expanduser("~")
        elif args[0] == "-":
            # Go to previous directory (stored in OLDPWD)
            target = context.variables.get("OLDPWD", old_pwd)
            if target == old_pwd:
                self._write("cd: OLDPWD not set\n", stdout)
                return
            # Print the directory we're switching to
            self._write(f"{target}\n", stdout)
        elif args[0] == "~" or args[0].startswith("~/"):
            target = os.path.expanduser(args[0])
        else:
            target = args[0]
        
        try:
            os.chdir(target)
            # Update OLDPWD after successful change
            context.variables["OLDPWD"] = old_pwd
            # Update PWD
            context.variables["PWD"] = os.getcwd()
        except FileNotFoundError:
            raise ArgumentError(self.name, [target], reason="no such file or directory")
        except NotADirectoryError:
            raise ArgumentError(self.name, [target], reason="not a directory")
        except PermissionError:
            raise ArgumentError(self.name, [target], reason="permission denied")
        except Exception as e:
            raise ArgumentError(self.name, [target], reason=str(e))

    def get_completer(self):
        from axonix.ui.completers.defaults import DirectoryCompleter
        return DirectoryCompleter()
