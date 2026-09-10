import re

from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError

_ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b",
    "f": "\f", "v": "\v", "e": "\x1b", "\\": "\\", '"': '"',
}
_SPEC = re.compile(r"%([-+ #0]*)(\d+|\*)?(?:\.(\d+|\*))?([sdiouxXfFeEgGc%])")


def _unescape(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if nxt == "0" or nxt.isdigit():
                j = i + 1
                digits = ""
                while j < len(text) and len(digits) < 3 and text[j] in "01234567":
                    digits += text[j]
                    j += 1
                if digits:
                    out.append(chr(int(digits, 8)))
                    i = j
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


class PrintfCommand(BaseCommand):
    help = "Format and print data"
    usage = "printf FORMAT [ARG...]"
    examples = [
        "printf '%s\\n' a b        - The format is reused for leftover args",
        "printf '%5d|%-5s|\\n' 42 x - Width and alignment",
        "printf '%.2f\\n' 3.14159  - Precision",
        "printf '%x %o %c\\n' 255 8 A",
    ]

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        self._require_args(args, min_count=1, error_msg="expected FORMAT")
        fmt, values = args[0], list(args[1:])
        status = 0
        chunks: list[str] = []

        def next_arg() -> str | None:
            return values.pop(0) if values else None

        def to_int(value: str | None) -> int:
            nonlocal status
            if value is None or value == "":
                return 0
            try:
                return int(value, 0) if value.lower().startswith(("0x", "0o", "0b")) else int(value)
            except ValueError:
                try:
                    return int(float(value))
                except ValueError:
                    self._write_err(f"printf: {value}: invalid number\n", stderr)
                    status = 1
                    return 0

        def to_float(value: str | None) -> float:
            nonlocal status
            if value is None or value == "":
                return 0.0
            try:
                return float(value)
            except ValueError:
                self._write_err(f"printf: {value}: invalid number\n", stderr)
                status = 1
                return 0.0

        def render_once() -> bool:
            """Render `fmt` once; return True if any argument was consumed."""
            consumed = False
            pos = 0
            for m in _SPEC.finditer(fmt):
                chunks.append(_unescape(fmt[pos:m.start()]))
                pos = m.end()
                flags, width, precision, conv = m.groups()
                if conv == "%":
                    chunks.append("%")
                    continue
                if width == "*":
                    width = str(to_int(next_arg()))
                    consumed = True
                if precision == "*":
                    precision = str(to_int(next_arg()))
                    consumed = True
                prec = "." + precision if precision is not None else ""
                spec = "%" + flags + (width or "") + prec
                arg = next_arg()
                consumed = consumed or arg is not None
                if conv in "di":
                    chunks.append((spec + "d") % to_int(arg))
                elif conv in "ouxX":
                    chunks.append((spec + conv) % to_int(arg))
                elif conv in "fFeEgG":
                    chunks.append((spec + conv) % to_float(arg))
                elif conv == "c":
                    chunks.append((spec + "s") % ((arg or "")[:1]))
                else:  # s
                    chunks.append((spec + "s") % (arg or ""))
            chunks.append(_unescape(fmt[pos:]))
            return consumed

        try:
            consumed = render_once()
            while values and consumed:
                consumed = render_once()
        except (ValueError, TypeError) as e:
            raise ArgumentError(self.name, fmt, reason=f"bad format: {e}") from None

        self._write("".join(chunks), stdout)
        return status
