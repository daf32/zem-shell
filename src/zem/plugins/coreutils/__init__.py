"""The small POSIX utilities, as a plugin.

`echo`, `printf`, `test`, `true` and `false` are commands a shell usually
has, but nothing in Zem depends on them: the parser, the executor and job
control neither call them nor know they exist. So they ship as a plugin,
and someone who would rather use `/bin/echo` can say so.
"""

from zem.plugin import Plugin
from zem.plugins.coreutils.echo import EchoCommand
from zem.plugins.coreutils.false import FalseCommand
from zem.plugins.coreutils.printf import PrintfCommand
from zem.plugins.coreutils.test import BracketCommand, TestExprCommand
from zem.plugins.coreutils.true import ColonCommand, TrueCommand


class CoreutilsPlugin(Plugin):
    name = "coreutils"
    version = "1.0.0"
    description = "echo, printf, test, [, true, false, :"

    def commands(self):
        return [
            EchoCommand, PrintfCommand,
            TestExprCommand, BracketCommand,
            TrueCommand, FalseCommand, ColonCommand,
        ]
