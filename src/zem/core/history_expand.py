"""bash-style history expansion: ``!!``, ``!$``, ``!N``, ``!-N``, ``!prefix``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from zem.core.scan import NORMAL, scan
from zem.errors.base_error import CLIError

if TYPE_CHECKING:
    from zem.config.settings import OperatorsConfig


class HistoryExpansionError(CLIError):
    exit_code = 1


def _last_word(entry: str) -> str:
    parts = entry.split()
    return parts[-1] if parts else ""


def _lookup(designator: str, history: Sequence[str]) -> str:
    if not history:
        raise HistoryExpansionError(f"!{designator}: event not found")
    if designator == "!":
        return history[-1]
    if designator == "$":
        return _last_word(history[-1])
    if designator.lstrip("-").isdigit():
        n = int(designator)
        index = len(history) + n if n < 0 else n - 1
        if 0 <= index < len(history):
            return history[index]
        raise HistoryExpansionError(f"!{designator}: event not found")
    for entry in reversed(history):
        if entry.startswith(designator):
            return entry
    raise HistoryExpansionError(f"!{designator}: event not found")


def expand_history(line: str, history: Sequence[str], ops: "OperatorsConfig") -> tuple[str, bool]:
    """Expand history designators in ``line``.

    Only an unquoted, unescaped ``!`` that starts a word is a designator;
    ``!`` followed by a blank, ``=``, or end of line is literal (so
    ``test a != b`` and ``echo hi!`` are untouched).

    Returns ``(expanded_line, changed)``. Raises
    :class:`HistoryExpansionError` for an unknown event.
    """
    chars, _, _ = scan(line, ops)
    out: list[str] = []
    changed = False
    i = 0
    n = len(line)
    while i < n:
        ch, escaped, state = chars[i]
        at_word_start = i == 0 or line[i - 1].isspace()
        if ch == "!" and not escaped and state == NORMAL and at_word_start and i + 1 < n:
            nxt = line[i + 1]
            if nxt in ("!", "$"):
                designator, end = nxt, i + 2
            elif nxt == "-" or nxt.isdigit():
                j = i + 2 if nxt == "-" else i + 1
                while j < n and line[j].isdigit():
                    j += 1
                designator, end = line[i + 1:j], j
                if designator in ("", "-"):
                    designator = None
            elif not nxt.isspace() and nxt != "=":
                j = i + 1
                while j < n and not line[j].isspace():
                    j += 1
                designator, end = line[i + 1:j], j
            else:
                designator = None
            if designator:
                out.append(_lookup(designator, history))
                changed = True
                i = end
                continue
        out.append(ch)
        i += 1
    return "".join(out), changed
