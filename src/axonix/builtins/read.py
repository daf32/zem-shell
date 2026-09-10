import getpass
import sys

from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError


class ReadCommand(BaseCommand):
    help = "Read a line from standard input into variables"
    usage = "read [-r] [-s] [-p PROMPT] [NAME...]"
    examples = [
        "read NAME                - Read a line into NAME",
        "read -p 'Name: ' NAME    - Prompt first",
        "read A B                 - Split on whitespace; B gets the rest",
        "read -s PASS             - Don't echo the input",
        "read                     - Read into REPLY",
    ]
    main_thread_only = True

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        raw = False
        silent = False
        prompt = ""
        names: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "-r":
                raw = True
            elif arg == "-s":
                silent = True
            elif arg == "-p":
                if i + 1 >= len(args):
                    raise ArgumentError(self.name, arg, reason="expected PROMPT")
                i += 1
                prompt = args[i]
            elif arg.startswith("-") and len(arg) > 1:
                raise ArgumentError(self.name, arg, reason="unknown option")
            else:
                names.append(arg)
            i += 1
        for name in names:
            self._validate_identifier(name)

        stream = stdin if stdin is not None else sys.stdin
        interactive = getattr(stream, "isatty", lambda: False)()
        if prompt and interactive:
            self._write(prompt, stdout)
            (stdout or sys.stdout).flush()

        if silent and interactive:
            try:
                line = getpass.getpass("")
            except EOFError:
                line = None
        else:
            text = stream.readline()
            line = None if text == "" else text.rstrip("\n")

        if line is None:
            return 1  # EOF

        if not raw:
            line = self._unescape(line)

        if not names:
            names = ["REPLY"]
        parts = line.split(None, len(names) - 1) if len(names) > 1 else [line.strip()]
        for idx, name in enumerate(names):
            value = parts[idx] if idx < len(parts) else ""
            context.set_var(name, value.rstrip() if idx == len(names) - 1 else value)
        return 0

    @staticmethod
    def _unescape(line: str) -> str:
        out: list[str] = []
        i = 0
        while i < len(line):
            if line[i] == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
            else:
                out.append(line[i])
                i += 1
        return "".join(out)
