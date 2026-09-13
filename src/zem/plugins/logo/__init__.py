"""The startup banner, as a plugin."""

from zem.plugin import Plugin
from zem.plugins.logo.command import LogoCommand


class LogoPlugin(Plugin):
    name = "logo"
    version = "1.0.0"
    description = "The `logo` banner"

    def commands(self):
        return [LogoCommand]
