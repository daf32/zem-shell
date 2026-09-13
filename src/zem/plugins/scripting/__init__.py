"""Running and inspecting commands, as a plugin.

`source`, `eval` and `exec` nest or replace execution; `read` reads a
line; `command` and `type` answer questions about what a name means.
Useful in scripts, unnecessary in a shell used only interactively.

Note that `command CMD` also has meaning in the parser, where it forces
an external lookup — that is core behaviour and stays whether or not this
plugin is loaded.
"""

from zem.plugin import Plugin
from zem.plugins.scripting.command import CommandCommand
from zem.plugins.scripting.eval import EvalCommand
from zem.plugins.scripting.exec import ExecCommand
from zem.plugins.scripting.read import ReadCommand
from zem.plugins.scripting.source import DotCommand, SourceCommand
from zem.plugins.scripting.type import TypeCommand


class ScriptingPlugin(Plugin):
    name = "scripting"
    version = "1.0.0"
    description = "source, ., eval, exec, read, command, type"

    def commands(self):
        return [
            SourceCommand, DotCommand, EvalCommand, ExecCommand,
            ReadCommand, CommandCommand, TypeCommand,
        ]
