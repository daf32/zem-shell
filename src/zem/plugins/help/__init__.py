"""The `help` command, as a plugin.

It reads the command registry and prints what it finds, so it works for
whatever is loaded — including commands from other plugins.
"""

from zem.plugin import Plugin
from zem.plugins.help.command import HelpCommand


class HelpPlugin(Plugin):
    name = "help"
    version = "1.0.0"
    description = "The `help` command"

    def commands(self):
        return [HelpCommand]
