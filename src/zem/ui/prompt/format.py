"""The prompt format mini-language.

A format string says what the prompt is made of, in what order, with what
literal text around it:

    "$venv$exit_code$path$git$symbol"
    " on [$branch]($style)"
    "($duration )"

Three constructs:

* ``$name`` (or ``${name}``) substitutes a module or, inside a module's own
  format, one of its variables.
* ``[text](style)`` styles what it contains; these nest.
* ``(...)`` is conditional: it renders only if something inside it produced
  output. That is how " on (branch)" disappears outside a repository
  without every module having to special-case its own punctuation.

Backslash escapes any of ``$ [ ] ( )``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Union

#: What a resolver may return for a variable: plain text, ready-made
#: `(style, text)` fragments, or None for "I have nothing".
Resolved = Union[str, list, None]
Resolver = Callable[[str], Resolved]
#: Maps a style name in a format string to a prompt_toolkit style.
StyleMap = Callable[[str], str]

_ESCAPABLE = "$[]()\\"


class FormatError(ValueError):
    """A format string could not be parsed."""


@dataclass
class Literal:
    text: str


@dataclass
class Variable:
    name: str


@dataclass
class Group:
    children: list = field(default_factory=list)
    style: Optional[str] = None


@dataclass
class Conditional:
    children: list = field(default_factory=list)


Node = Union[Literal, Variable, Group, Conditional]


def parse(text: str) -> list:
    """Parse a format string into nodes."""
    nodes, index = _parse_until(text, 0, closing=None)
    if index != len(text):
        raise FormatError(f"unexpected {text[index]!r} at position {index}")
    return nodes


def _parse_until(text: str, index: int, closing: Optional[str]) -> tuple:
    nodes: list = []
    buffer: list = []

    def flush() -> None:
        if buffer:
            nodes.append(Literal("".join(buffer)))
            buffer.clear()

    while index < len(text):
        char = text[index]

        if closing is not None and char == closing:
            flush()
            return nodes, index

        if char == "\\":
            if index + 1 >= len(text):
                raise FormatError("trailing backslash")
            nxt = text[index + 1]
            buffer.append(nxt if nxt in _ESCAPABLE else "\\" + nxt)
            index += 2
            continue

        if char == "$":
            name, index = _parse_name(text, index + 1)
            flush()
            nodes.append(Variable(name))
            continue

        if char == "[":
            flush()
            children, index = _parse_until(text, index + 1, closing="]")
            if index >= len(text):
                raise FormatError("unclosed '['")
            index += 1  # past ']'
            if index >= len(text) or text[index] != "(":
                raise FormatError("a '[...]' group must be followed by '(style)'")
            style, index = _parse_style(text, index + 1)
            nodes.append(Group(children, style))
            continue

        if char == "(":
            flush()
            children, index = _parse_until(text, index + 1, closing=")")
            if index >= len(text):
                raise FormatError("unclosed '('")
            index += 1  # past ')'
            nodes.append(Conditional(children))
            continue

        if char in "])":
            raise FormatError(f"unexpected {char!r} at position {index}")

        buffer.append(char)
        index += 1

    if closing is not None:
        raise FormatError(f"unclosed {closing!r}")
    flush()
    return nodes, index


def _parse_name(text: str, index: int) -> tuple:
    if index < len(text) and text[index] == "{":
        end = text.find("}", index)
        if end == -1:
            raise FormatError("unclosed '${'")
        return text[index + 1:end], end + 1

    start = index
    while index < len(text) and (text[index].isalnum() or text[index] == "_"):
        index += 1
    if index == start:
        raise FormatError(f"empty variable name at position {start}")
    return text[start:index], index


def _parse_style(text: str, index: int) -> tuple:
    end = text.find(")", index)
    if end == -1:
        raise FormatError("unclosed '(' in a style")
    return text[index:end].strip(), end + 1


def render(nodes: list, resolve: Resolver, style_map: Optional[StyleMap] = None,
           style: str = "") -> list:
    """Render nodes into `(style, text)` fragments."""
    fragments: list = []
    for node in nodes:
        fragments.extend(_render_node(node, resolve, style_map or (lambda s: s), style))
    return fragments


def _render_node(node: Node, resolve: Resolver, style_map: StyleMap, style: str) -> list:
    if isinstance(node, Literal):
        return [(style, node.text)] if node.text else []

    if isinstance(node, Variable):
        value = resolve(node.name)
        if value is None:
            return []
        if isinstance(value, str):
            return [(style, value)] if value else []
        # Ready-made fragments (a module rendered its own format already).
        return list(value)

    if isinstance(node, Group):
        inner = style_map(node.style) if node.style else style
        return render(node.children, resolve, style_map, inner)

    if isinstance(node, Conditional):
        produced = render(node.children, resolve, style_map, style)
        # Literal text alone is not "something": "( on $branch)" should
        # vanish when there is no branch, punctuation and all.
        if any(_has_variable(child) for child in node.children):
            if not _any_variable_resolved(node.children, resolve):
                return []
        return produced

    raise FormatError(f"unknown node {node!r}")


def _has_variable(node: Node) -> bool:
    if isinstance(node, Variable):
        return True
    if isinstance(node, (Group, Conditional)):
        return any(_has_variable(child) for child in node.children)
    return False


def _any_variable_resolved(nodes: list, resolve: Resolver) -> bool:
    for node in nodes:
        if isinstance(node, Variable):
            if resolve(node.name):
                return True
        elif isinstance(node, (Group, Conditional)):
            if _any_variable_resolved(node.children, resolve):
                return True
    return False
