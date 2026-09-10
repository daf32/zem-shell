"""Quoting helpers shared by builtins that print re-sourceable output."""


def sh_quote(value: str) -> str:
    """Single-quote ``value`` so the shell parser reads it back verbatim.

    Always quotes (like bash's `alias`/`export -p` output) and escapes
    embedded single quotes as ``'\\''``, which the Axonix parser joins into
    one token.
    """
    return "'" + value.replace("'", "'\\''") + "'"
