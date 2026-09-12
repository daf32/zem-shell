"""HintSpec schema: what a spec may say and how it fails."""

import pytest

from zem.hints.spec import CURRENT_SCHEMA_VERSION, SpecError, parse_spec


def _spec(**extra):
    return {"schema_version": 1, "command": "demo", **extra}


def test_minimal_spec():
    spec = parse_spec(_spec())
    assert spec.command == "demo"
    assert spec.fallback == "files"
    assert spec.origin == "bundled"


def test_aliases_are_extra_names():
    assert parse_spec(_spec(command="pip", aliases=["pip3"])).names() == ["pip", "pip3"]


def test_nested_subcommands():
    spec = parse_spec(_spec(subcommands=[
        {"name": "container", "subcommands": [{"name": "ls", "description": "List"}]},
    ]))
    assert spec.subcommands[0].subcommands[0].name == "ls"


def test_future_schema_version_is_refused():
    with pytest.raises(SpecError, match="upgrade zem"):
        parse_spec(_spec(schema_version=CURRENT_SCHEMA_VERSION + 1))


def test_unknown_key_is_an_error():
    # A typo must fail loudly instead of silently doing nothing.
    with pytest.raises(SpecError, match="subcommand"):
        parse_spec(_spec(subcommand=[]))


def test_not_an_object():
    with pytest.raises(SpecError, match="JSON object"):
        parse_spec([1, 2, 3])


def test_option_name_needs_a_dash():
    with pytest.raises(SpecError, match="must start with a dash"):
        parse_spec(_spec(options=[{"names": ["upgrade"]}]))


def test_variadic_positional_must_be_last():
    with pytest.raises(SpecError, match="variadic"):
        parse_spec(_spec(args=[
            {"name": "first", "variadic": True},
            {"name": "second"},
        ]))


def test_command_source_rejects_placeholders():
    # Splicing user input into an argv would be an injection vector.
    with pytest.raises(SpecError, match="placeholders"):
        parse_spec(_spec(args=[{
            "name": "branch",
            "source": {"type": "command", "run": ["git", "branch", "--list", "{word}"]},
        }]))


def test_command_source_needs_argv():
    with pytest.raises(SpecError):
        parse_spec(_spec(args=[{"name": "x", "source": {"type": "command", "run": []}}]))


@pytest.mark.parametrize("timeout", [0, 5000])
def test_command_timeout_is_bounded(timeout):
    with pytest.raises(SpecError):
        parse_spec(_spec(args=[{
            "name": "x",
            "source": {"type": "command", "run": ["true"], "timeout_ms": timeout},
        }]))


def test_provider_name_must_be_namespaced():
    with pytest.raises(SpecError):
        parse_spec(_spec(args=[{"name": "x", "source": {"type": "provider", "name": "branches"}}]))


def test_values_source_accepts_plain_strings_and_objects():
    spec = parse_spec(_spec(args=[{
        "name": "mode",
        "source": {"type": "values", "items": ["on", {"value": "off", "description": "Disable"}]},
    }]))
    choices = spec.args[0].source.choices()
    assert [(c.value, c.description) for c in choices] == [("on", ""), ("off", "Disable")]


def test_any_of_nests_sources():
    spec = parse_spec(_spec(args=[{
        "name": "target",
        "source": {"type": "any_of", "sources": [
            {"type": "provider", "name": "git.branches"},
            {"type": "files"},
        ]},
    }]))
    assert [s.type for s in spec.args[0].source.sources] == ["provider", "files"]
