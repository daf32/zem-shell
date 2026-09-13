"""Colour themes, as a plugin.

Themes are not something the shell needs in order to be a shell, so they
ship as a plugin: `plugin disable theme` takes the command and the bundled
themes with it.
"""

from pathlib import Path

from zem.plugin import Plugin
from zem.plugins.theme.command import ThemeCommand

THEMES_DIR = Path(__file__).parent / "themes"


class ThemePlugin(Plugin):
    name = "theme"
    version = "1.0.0"
    description = "Colour themes and the `theme` command"

    def commands(self):
        return [ThemeCommand]

    def themes(self):
        return [str(THEMES_DIR)]
