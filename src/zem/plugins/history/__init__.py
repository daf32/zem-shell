"""The `history` command, as a plugin.

Recording history, expanding `!!` and searching it with Ctrl-R are the
shell's own; this is the command that lists and prunes it.
"""

from zem.plugin import Plugin
from zem.plugins.history.command import HistoryCommand


class HistoryPlugin(Plugin):
    name = "history"
    version = "1.0.0"
    description = "The `history` command"

    def commands(self):
        return [HistoryCommand]
