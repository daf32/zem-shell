"""The directory stack, as a plugin.

`pushd`/`popd`/`dirs` are a convenience over `cd`. The stack itself lives
on the execution context, so nothing breaks when this is switched off —
there is simply no way to push onto it.
"""

from zem.plugin import Plugin
from zem.plugins.dirstack.dirs import DirsCommand
from zem.plugins.dirstack.popd import PopdCommand
from zem.plugins.dirstack.pushd import PushdCommand


class DirstackPlugin(Plugin):
    name = "dirstack"
    version = "1.0.0"
    description = "pushd, popd, dirs"

    def commands(self):
        return [PushdCommand, PopdCommand, DirsCommand]
