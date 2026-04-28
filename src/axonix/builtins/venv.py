from axonix.builtins.base import BaseCommand
from axonix.utils.venv import activate_venv, deactivate_venv, find_venv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext

class VenvCommand(BaseCommand):
    name = "venv"
    help = "Manage Python virtual environments (activate/deactivate)"
    usage = "venv [activate|deactivate]"
    tags = ["builtin", "python"]

    def execute(self, args: list, context: "ExecutionContext", stdin=None, stdout=None):
        if not args:
            if context.active_venv:
                self._write(f"✓ Active venv: {context.active_venv}\n", stdout)
            else:
                self._write("✗ No venv active\n", stdout)
            return

        subcommand = args[0].lower()

        if subcommand == "activate":
            from pathlib import Path
            venv_path = find_venv(Path.cwd())
            if venv_path:
                activate_venv(context)
                self._write(f"✓ Activated venv: {venv_path}\n", stdout)
            else:
                self._write("✗ No virtual environment found in current directory or parents\n", stdout)
        
        elif subcommand == "deactivate":
            if context.active_venv:
                deactivate_venv(context)
                self._write("✓ Deactivated venv\n", stdout)
            else:
                self._write("✗ No venv is currently active\n", stdout)
        
        elif subcommand == "on":
            pass
        elif subcommand == "off":
            pass
        else:
            self._write(f"Unknown subcommand: {subcommand}\n", stdout)
            self._write(f"Usage: {self.usage}\n", stdout)

