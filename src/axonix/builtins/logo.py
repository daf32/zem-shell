from axonix.builtins.base import BaseCommand
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


class LogoCommand(BaseCommand):
    help = "Display Axonix logo"
    usage = "logo"
    tags = ["builtin", "ui"]

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ):
        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText
        from axonix.config.settings import AppConfig
        
        config = AppConfig()
        c = config.colors
        
        # Build logo with proper colors from config
        lines = [
            ("     █████╗ ██╗  ██╗ ██████╗ ███╗   ██╗██╗██╗  ██╗", c.logo_primary),
            ("    ██╔══██╗╚██╗██╔╝██╔═══██╗████╗  ██║██║╚██╗██╔╝", c.logo_secondary),
            ("    ███████║ ╚███╔╝ ██║   ██║██╔██╗ ██║██║ ╚███╔╝ ", c.logo_primary),
            ("    ██╔══██║ ██╔██╗ ██║   ██║██║╚██╗██║██║ ██╔██╗ ", c.logo_secondary),
            ("    ██║  ██║██╔╝ ██╗╚██████╔╝██║ ╚████║██║██╔╝ ██╗", c.logo_tertiary),
            ("    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝", c.logo_primary),
        ]
        
        for text, color in lines:
            print_formatted_text(FormattedText([(color, text)]))
