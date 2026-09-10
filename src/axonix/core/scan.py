"""Quote/escape-aware character scanner shared by the parser and the UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.config.settings import OperatorsConfig

NORMAL, SINGLE, DOUBLE, SUBST = range(4)


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
