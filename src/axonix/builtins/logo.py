from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class LogoCommand(BaseCommand):
    help = "Display Axonix logo"
    usage = "logo [--version]"
    tags = ["builtin", "ui"]

    VERSION = "0.1.0"

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText
        
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
        
        print_formatted_text(FormattedText([("", "")]))  # Empty line
        for text, color in lines:
            print_formatted_text(FormattedText([(color, text)]))
        
        # Show version if requested or just show tagline
        if args and args[0] in ("--version", "-v"):
            print_formatted_text(FormattedText([
                ("", "\n"),
                (c.info, f"    Axonix Shell v{self.VERSION}"),
                ("", "\n"),
            ]))
        else:
            print_formatted_text(FormattedText([
                ("", "\n"),
                (c.comment, "    A modern shell for developers"),
                ("", "\n"),
            ]))
