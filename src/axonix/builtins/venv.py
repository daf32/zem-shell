from pathlib import Path
from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError
from axonix.utils.venv import activate_venv, deactivate_venv, find_venv, is_valid_venv

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class VenvCommand(BaseCommand):
    name = "venv"
    help = "Manage Python virtual environments (activate/deactivate)"
    usage = "venv [activate [PATH] | deactivate]"
    tags = ["builtin", "python"]
    examples = [
        "venv                 - Show the active venv",
        "venv activate        - Activate the nearest .venv/venv/env",
        "venv activate ~/env  - Activate a specific venv",
        "venv deactivate      - Deactivate",
    ]

    def execute(
        self,
        args: list,
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,
    ) -> int:
        if not args:
            if context.active_venv:
                self._write(f"✓ Active venv: {context.active_venv}\n", stdout)
            else:
                self._write("✗ No venv active\n", stdout)
            return 0

        subcommand = args[0].lower()

        if subcommand == "activate":
            if len(args) > 2:
                raise ArgumentError(self.name, args, reason="too many arguments")
            if len(args) == 2:
                path = Path(args[1]).expanduser()
                if not is_valid_venv(path):
                    self._write_err(f"venv: {path}: not a virtual environment\n", stderr)
                    return 1
            else:
                path = find_venv(Path.cwd())
                if path is None:
                    self._write_err(
                        "venv: no virtual environment found in current directory or parents\n",
                        stderr,
                    )
                    return 1
            activate_venv(context, path)
            self._write(f"✓ Activated venv: {path}\n", stdout)
            return 0

        if subcommand == "deactivate":
            if not deactivate_venv(context):
                self._write_err("venv: no venv is currently active\n", stderr)
                return 1
            self._write("✓ Deactivated venv\n", stdout)
            return 0

        raise ArgumentError(self.name, subcommand, reason="unknown subcommand")
