"""Working out what the user is completing, given a spec and a command line.

Kept free of I/O and of prompt_toolkit on purpose: this is the part with
all the edge cases, and it is far easier to test as a pure function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Union

from zem.hints.spec import HintSpec, Node, Option, Positional

SpecNode = Union[HintSpec, Node]

_REDIRECT_CHARS = "<>&"


@dataclass
class Resolution:
    """What to offer at the cursor."""

    node: SpecNode
    path: tuple[str, ...]
    offer_subcommands: bool = False
    offer_flags: bool = False
    #: Value sources for the position under the cursor.
    sources: tuple = ()
    #: Flags visible here, own and inherited.
    options: tuple[Option, ...] = ()
    positional: Optional[Positional] = None
    #: `--flag=val`: how many characters of the word are not part of the value.
    value_offset: int = 0
    #: The cursor is naming a redirection target, not an argument.
    redirect_target: bool = False
    extra: dict = field(default_factory=dict)


def resolve(spec: HintSpec, values: Sequence[str], cursor_index: int,
            prefix: str = "") -> Resolution:
    """Resolve the cursor position against `spec`.

    `values` is the whole command line as words (aliases already expanded),
    `cursor_index` the index of the word being typed — which may be one
    past the end when the user just hit space.
    """
    typed = [w for w in values[1:cursor_index]]
    typed, redirect_target = _strip_redirections(typed)
    if redirect_target:
        return Resolution(spec, (spec.command,), redirect_target=True)

    node: SpecNode = spec
    path = [spec.command]
    inherited = [o for o in spec.options if o.inherited]
    positionals_seen = 0
    after_terminator = False
    pending: Optional[Option] = None
    lost = False

    for word in typed:
        if pending is not None:
            pending = None
            continue
        if word == "--" and not after_terminator:
            after_terminator = True
            continue
        if not after_terminator and _looks_like_flag(word):
            pending = _consume_flag(word, node, inherited)
            continue

        child = _find_child(node, word) if positionals_seen == 0 else None
        if child is not None:
            node = child
            path.append(child.name)
            inherited += [o for o in child.options if o.inherited]
            positionals_seen = 0
        elif node.args:
            positionals_seen += 1
        elif getattr(node, "subcommands", None):
            # An unknown subcommand: everything past it is guesswork, so
            # offer nothing rather than something wrong.
            lost = True
        else:
            positionals_seen += 1

    options = tuple(o for o in (*node.options, *inherited) if not o.hidden)
    base = Resolution(node=node, path=tuple(path), options=options)

    if pending is not None and pending.value is not None:
        base.sources = (pending.value,)
        return base

    # A bare `-` or `--` under the cursor is someone asking "what flags are
    # there?" -- unlike a *completed* `-`, which means stdin.
    if not after_terminator and prefix.startswith("-"):
        name, eq, _ = prefix.partition("=")
        option = _find_option(node, inherited, name)
        if eq and option is not None and option.value is not None:
            base.sources = (option.value,)
            base.value_offset = len(name) + 1
            return base
        base.offer_flags = True
        return base

    if lost:
        return base

    base.offer_subcommands = bool(getattr(node, "subcommands", None)) and positionals_seen == 0
    positional = _positional_at(node, positionals_seen)
    if positional is not None:
        base.positional = positional
        base.sources = (positional.source,)
    return base


def _looks_like_flag(word: str) -> bool:
    return word.startswith("-") and word not in ("-", "--")


def _consume_flag(word: str, node: SpecNode, inherited: list[Option]) -> Optional[Option]:
    """Return the option whose value the *next* word will be, if any."""
    name, eq, _ = word.partition("=")
    option = _find_option(node, inherited, name)
    if option is None and not eq and not name.startswith("--") and len(name) > 2:
        # A short flag with its value glued on (`-p8080`): the value is
        # already inside this word, so the next word is not it.
        glued = _find_option(node, inherited, name[:2])
        if glued is not None and glued.value is not None:
            return None
    if option is not None and option.value is not None and not eq:
        return option
    return None


def _find_option(node: SpecNode, inherited: list[Option], name: str) -> Optional[Option]:
    for option in (*node.options, *inherited):
        if name in option.names:
            return option
    return None


def _find_child(node: SpecNode, word: str) -> Optional[Node]:
    for child in getattr(node, "subcommands", ()):
        if word == child.name or word in child.aliases:
            return child
    return None


def _positional_at(node: SpecNode, index: int) -> Optional[Positional]:
    if index < len(node.args):
        return node.args[index]
    if node.args and node.args[-1].variadic:
        return node.args[-1]
    return None


def _strip_redirections(words: list[str]) -> tuple[list[str], bool]:
    """Drop `> file` pairs; report whether the cursor is naming a target.

    `git add > out.txt` used to count `>` and `out.txt` as positional
    arguments of `add`, shifting everything after them.
    """
    out: list[str] = []
    expect_target = False
    for word in words:
        if expect_target:
            expect_target = False
            continue
        if _is_redirect(word):
            expect_target = True
            continue
        out.append(word)
    return out, expect_target


def _is_redirect(word: str) -> bool:
    body = word[1:] if word[:1].isdigit() else word
    return bool(body) and all(c in _REDIRECT_CHARS for c in body)
