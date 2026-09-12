"""Quote/escape-aware character scanner shared by the parser and the UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zem.config.settings import OperatorsConfig

NORMAL, SINGLE, DOUBLE, SUBST = range(4)

#: Characters that start a redirection operator. A word made of these (plus a
#: leading fd digit) is shell syntax, not an argument of the command.
_REDIRECT_CHARS = "<>&"


def scan(text: str, ops: "OperatorsConfig") -> tuple[list[tuple[str, bool, int]], int, bool]:
    """Classify every character of ``text``.

    Returns ``(chars, final_state, dangling_escape)`` where ``chars`` is a
    list of ``(char, escaped, state)``. ``state`` is ``SUBST`` while inside
    ``$( ... )`` at any depth, otherwise ``NORMAL``/``SINGLE``/``DOUBLE``.
    ``dangling_escape`` is true when the text ends with an unconsumed
    escape character (i.e. a line continuation).
    """
    chars: list[tuple[str, bool, int]] = []
    state = NORMAL
    escaped = False
    depth = 0
    for i, ch in enumerate(text):
        chars.append((ch, escaped, SUBST if depth else state))

        if escaped:
            escaped = False
        elif ch == ops.escape and state != SINGLE:
            escaped = True
        elif state == NORMAL:
            if ch == ops.quote:
                state = SINGLE
            elif ch == ops.double_quote:
                state = DOUBLE
            elif ch == ops.variable and text[i + 1:i + 2] == "(":
                depth += 1
            elif ch == ")" and depth:
                depth -= 1
        elif state == SINGLE and ch == ops.quote:
            state = NORMAL
        elif state == DOUBLE:
            if ch == ops.double_quote:
                state = NORMAL
            elif ch == ops.variable and text[i + 1:i + 2] == "(":
                depth += 1
            elif ch == ")" and depth:
                depth -= 1

    if depth:
        state = SUBST
    return chars, state, escaped


def needs_continuation(text: str, ops: "OperatorsConfig") -> bool:
    """True when ``text`` is an incomplete command line.

    Incomplete means: a trailing unescaped backslash, an unclosed quote or
    ``$(``, or a trailing pipe / ``&&`` / ``||`` operator.
    """
    chars, state, dangling = scan(text, ops)
    if dangling or state != NORMAL:
        return True

    # Trailing operator: look at the last non-blank character(s) and make
    # sure they are unquoted operator characters, not text.
    stripped = text.rstrip()
    if not stripped:
        return False
    last = chars[len(stripped) - 1]
    if last[1] or last[2] != NORMAL:
        return False
    if stripped.endswith(ops.pipe):
        return True
    if stripped.endswith(ops.and_if):
        prev = chars[len(stripped) - 2] if len(stripped) >= 2 else None
        return prev is not None and not prev[1] and prev[2] == NORMAL
    return False


def join_lines(first: str, second: str, ops: "OperatorsConfig") -> str:
    """Join a continued line with its continuation.

    A trailing backslash is removed and the lines are glued directly (bash
    semantics); otherwise the newline is kept so quoted text spans lines.
    """
    _, state, dangling = scan(first, ops)
    if dangling:
        return first[:-1] + second
    return first + "\n" + second


@dataclass(frozen=True)
class Word:
    """One word of a command line, with its position in the source text.

    ``text`` is the raw slice (quotes and escapes kept), ``value`` is what
    the word means once quoting is resolved. Completion needs both: the raw
    length to compute ``start_position``, the value to match a prefix
    against.
    """

    text: str
    value: str
    start: int
    end: int
    is_redirect: bool = False


def split_words(text: str, ops: "OperatorsConfig") -> list[Word]:
    """Split ``text`` into words, honouring quotes and escapes.

    Unlike :meth:`zem.core.parser.Parser._tokenize` this performs no
    expansion whatsoever: no variables, no globs and — crucially — no
    ``$(...)`` substitution. Completion runs on every keystroke, so running
    a command just to split a line would be a disaster.
    """
    chars, _, _ = scan(text, ops)
    words: list[Word] = []
    buf: list[str] = []
    start = -1

    def flush(end: int) -> None:
        nonlocal start, buf
        if start >= 0:
            raw = text[start:end]
            words.append(Word(raw, "".join(buf), start, end, _is_redirect(raw)))
            buf = []
            start = -1

    for i, (ch, escaped, state) in enumerate(chars):
        if not escaped and state == NORMAL and ch.isspace():
            flush(i)
            continue

        # Quote and escape characters delimit the word but are not part of
        # its value. `scan` records the state *before* the transition, so an
        # opening quote carries NORMAL and the closing one carries its own
        # state -- hence two states per quote character.
        is_syntax = not escaped and (
            (ch == ops.escape and state in (NORMAL, DOUBLE))
            or (ch == ops.quote and state in (NORMAL, SINGLE))
            or (ch == ops.double_quote and state in (NORMAL, DOUBLE))
        )

        if start < 0:
            start = i
        if not is_syntax:
            buf.append(ch)

    flush(len(text))
    return words


def _is_redirect(raw: str) -> bool:
    """True for a bare redirection operator (`>`, `>>`, `2>`, `&>` ...)."""
    body = raw[1:] if raw[:1].isdigit() else raw
    return bool(body) and all(c in _REDIRECT_CHARS for c in body)


def word_at(text: str, ops: "OperatorsConfig") -> tuple[list[Word], int]:
    """Words of ``text`` plus the index of the one under the cursor.

    ``text`` is the text *before* the cursor, so the cursor sits on the last
    word unless the line ends on a separator, in which case the index is
    ``-1``: the user is starting a new word.
    """
    words = split_words(text, ops)
    if words and words[-1].end == len(text):
        return words, len(words) - 1
    return words, -1
