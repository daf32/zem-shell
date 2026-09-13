"""Python virtualenv activation, as a plugin.

A shell that is not bash cannot `source` a virtualenv's `activate` script
— it is bash, with functions and `if`. So the work is done in Python, the
way xonsh's `vox` does it, and it lives here rather than in the core:
plenty of people never touch Python.
"""

from zem.plugin import Plugin
from zem.plugins.venv.command import VenvCommand


class VenvPlugin(Plugin):
    name = "venv"
    version = "1.0.0"
    description = "The `venv` command and prompt module"

    def commands(self):
        return [VenvCommand]
