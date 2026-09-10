from typing import TYPE_CHECKING

from axonix.builtins.base import BaseCommand

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
    "f": "\f", "v": "\v", "e": "\x1b", "\\": "\\", "0": "\0",
}


def _unescape(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in _ESCAPES:
            out.append(_ESCAPES[text[i + 1]])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


class EchoCommand(BaseCommand):
    help = "Print arguments"
    usage = "echo [-n] [-e|-E] [text...]"
    examples = [
        "echo hello world      - Print text",
        "echo -n no newline    - Suppress the trailing newline",
        "echo -e 'a\\tb'        - Interpret backslash escapes",
    ]

    def execute(
        self, args: list[str], context: "ExecutionContext", stdin=None, stdout=None
    ) -> int:
        newline = True
        interpret = False
        i = 0
        # Like bash: options are only recognised at the start and must be
        # made solely of the known flag letters; anything else is text.
        while i < len(args) and len(args[i]) > 1 and args[i][0] == "-" \
                and set(args[i][1:]) <= {"n", "e", "E"}:
            flags = args[i][1:]
            if "n" in flags:
                newline = False
            if "e" in flags:
                interpret = True
            if "E" in flags:
                interpret = False
            i += 1

        text = " ".join(args[i:])
        if interpret:
            text = _unescape(text)
        self._write(text + ("\n" if newline else ""), stdout)
        return 0
