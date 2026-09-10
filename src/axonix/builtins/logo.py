from typing import TYPE_CHECKING

from axonix import __version__
from axonix.builtins.base import BaseCommand

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class LogoCommand(BaseCommand):
    help = "Display Axonix logo"
    usage = "logo [--version]"
    tags = ["builtin", "ui"]

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        
        # Get colors from shell config if available
        c = None
        if hasattr(context, "_shell") and context._shell:
            c = context._shell.config.colors
        else:
            from axonix.config.settings import AppConfig
            c = AppConfig().colors
        
        # Build logo with proper colors from config
        lines = [
            ("     █████╗ ██╗  ██╗ ██████╗ ███╗   ██╗██╗██╗  ██╗", c.logo_primary),
            ("    ██╔══██╗╚██╗██╔╝██╔═══██╗████╗  ██║██║╚██╗██╔╝", c.logo_secondary),
            ("    ███████║ ╚███╔╝ ██║   ██║██╔██╗ ██║██║ ╚███╔╝ ", c.logo_primary),
            ("    ██╔══██║ ██╔██╗ ██║   ██║██║╚██╗██║██║ ██╔██╗ ", c.logo_secondary),
            ("    ██║  ██║██╔╝ ██╗╚██████╔╝██║ ╚████║██║██╔╝ ██╗", c.logo_tertiary),
            ("    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝", c.logo_primary),
        ]
        
        self._print_colored([("", "")], stdout)  # Empty line
        for text, color in lines:
            self._print_colored([(color, text)], stdout)
        
        # Show version if requested or just show tagline
        if args and args[0] in ("--version", "-v"):
            self._print_colored([
                ("", "\n"),
                (c.info, f"    Axonix Shell v{__version__}"),
                ("", "\n"),
            ], stdout)
        else:
            self._print_colored([
                ("", "\n"),
                (c.comment, "    A modern shell for developers"),
                ("", "\n"),
            ], stdout)
