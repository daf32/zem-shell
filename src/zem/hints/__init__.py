"""Declarative completion hints.

A hint spec is a JSON document describing one command: its subcommands,
its flags, its positional arguments and where the values for each come
from. `SpecCompleter` executes a spec, so adding completion for a new
tool means writing JSON, not Python.
"""

from zem.hints.spec import (
    CURRENT_SCHEMA_VERSION,
    HintSpec,
    Node,
    Option,
    Positional,
    SpecError,
    parse_spec,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "HintSpec",
    "Node",
    "Option",
    "Positional",
    "SpecError",
    "parse_spec",
]
