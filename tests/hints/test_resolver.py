"""Resolver: where is the cursor, and what belongs there."""

import pytest

from zem.hints.resolver import resolve
from zem.hints.spec import parse_spec

SPEC = {
    "schema_version": 1,
    "command": "demo",
    "options": [
        {"names": ["-C"], "description": "Elsewhere", "inherited": True,
         "value": {"type": "dirs"}},
        {"names": ["--version"], "description": "Print version"},
    ],
    "subcommands": [
        {
            "name": "run",
            "aliases": ["r"],
            "options": [
                {"names": ["-f", "--fast"], "description": "Quick"},
                {"names": ["--mode"], "value": {"type": "values", "items": ["dev", "prod"]}},
                {"names": ["-p"], "value": {"type": "none"}},
            ],
            "args": [
                {"name": "target", "source": {"type": "values", "items": ["a", "b"]}},
                {"name": "rest", "variadic": True, "source": {"type": "files"}},
            ],
        },
        {
            "name": "remote",
            "subcommands": [
                {"name": "add", "args": [{"name": "name", "source": {"type": "none"}}]},
                {"name": "show"},
            ],
        },
    ],
}


@pytest.fixture
def spec():
    return parse_spec(SPEC)


def _resolve(spec, line, prefix=""):
    """`line` is the words already typed; `prefix` the word being typed."""
    words = line.split()
    if prefix:
        words = words + [prefix]
        return resolve(spec, words, len(words) - 1, prefix)
    return resolve(spec, words, len(words), prefix)


def test_subcommands_at_top_level(spec):
    res = _resolve(spec, "demo")
    assert res.offer_subcommands
    assert res.path == ("demo",)


def test_descends_into_a_subcommand(spec):
    res = _resolve(spec, "demo remote")
    assert res.path == ("demo", "remote")
    assert res.offer_subcommands


def test_descends_through_an_alias(spec):
    assert _resolve(spec, "demo r").path == ("demo", "run")


def test_nested_subcommand(spec):
    res = _resolve(spec, "demo remote add")
    assert res.path == ("demo", "remote", "add")
    assert not res.offer_subcommands
    assert res.positional.name == "name"


def test_flag_prefix_offers_flags(spec):
    res = _resolve(spec, "demo run", prefix="--f")
    assert res.offer_flags
    assert not res.offer_subcommands


def test_bare_dash_offers_flags(spec):
    assert _resolve(spec, "demo run", prefix="-").offer_flags


def test_inherited_flags_are_visible_deeper(spec):
    res = _resolve(spec, "demo remote add", prefix="-")
    assert "-C" in {name for o in res.options for name in o.names}


def test_flag_awaiting_a_value(spec):
    res = _resolve(spec, "demo run --mode")
    assert not res.offer_subcommands
    assert res.sources[0].type == "values"


def test_inline_flag_value(spec):
    res = _resolve(spec, "demo run", prefix="--mode=de")
    assert res.sources[0].type == "values"
    assert res.value_offset == len("--mode=")


def test_flag_value_does_not_count_as_positional(spec):
    # `--mode dev a` -> `a` is the *first* positional, not the second.
    res = _resolve(spec, "demo run --mode dev")
    assert res.positional.name == "target"


def test_positional_index_advances(spec):
    assert _resolve(spec, "demo run a").positional.name == "rest"


def test_variadic_positional_repeats(spec):
    assert _resolve(spec, "demo run a b c d").positional.name == "rest"


def test_flags_do_not_shift_positionals(spec):
    assert _resolve(spec, "demo run --fast").positional.name == "target"


def test_glued_short_flag_value(spec):
    # `-pdev` carries its value inside the word; the next word is a
    # positional, not the flag's value.
    assert _resolve(spec, "demo run -pdev").positional.name == "target"


def test_terminator_ends_flag_parsing(spec):
    res = _resolve(spec, "demo run --", prefix="--fast")
    assert not res.offer_flags


def test_subcommands_stop_after_a_positional(spec):
    assert not _resolve(spec, "demo run a").offer_subcommands


def test_unknown_subcommand_offers_nothing(spec):
    res = _resolve(spec, "demo frobnicate")
    assert not res.offer_subcommands and res.sources == ()


def test_redirection_target(spec):
    res = _resolve(spec, "demo run >")
    assert res.redirect_target


def test_redirection_does_not_shift_positionals(spec):
    # `> out.txt` is shell syntax, not an argument of `run`.
    assert _resolve(spec, "demo run > out.txt").positional.name == "target"
