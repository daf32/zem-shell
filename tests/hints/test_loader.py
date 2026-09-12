"""Spec discovery: where specs come from and what a broken one does."""

import json

import pytest

from zem.hints.loader import ENV_PATH, HintRegistry


@pytest.fixture
def user_dir(tmp_path):
    path = tmp_path / "hints"
    path.mkdir()
    return path


def _write(directory, name, **spec):
    payload = {"schema_version": 1, "command": name, **spec}
    (directory / f"{name}.json").write_text(json.dumps(payload))


def test_bundled_specs_all_parse():
    # A regression net over every spec we ship: nothing else type-checks
    # JSON, and a broken one would silently stop completing.
    registry = HintRegistry(user_dir="/nonexistent")
    specs = registry.load()
    assert registry.errors() == {}
    assert {
        "git", "pip", "pip3", "docker", "npm", "npx", "uv", "kubectl",
        "brew", "gh", "ssh", "make", "go", "theme", "config", "weather",
    } <= set(specs)


def test_aliases_register_extra_names():
    registry = HintRegistry(user_dir="/nonexistent")
    assert registry.get("pip3") is registry.get("pip")


def test_user_spec_overrides_a_bundled_one(user_dir):
    _write(user_dir, "git", description="mine")
    registry = HintRegistry(user_dir=str(user_dir))
    spec = registry.get("git")
    assert spec.description == "mine"
    assert spec.origin == "user"


def test_env_path_is_searched(user_dir, monkeypatch):
    _write(user_dir, "mytool", description="from env")
    monkeypatch.setenv(ENV_PATH, str(user_dir))
    assert HintRegistry(user_dir="/nonexistent").get("mytool").description == "from env"


def test_broken_json_is_reported_not_raised(user_dir):
    (user_dir / "broken.json").write_text("{not json")
    _write(user_dir, "fine")
    registry = HintRegistry(user_dir=str(user_dir))
    assert registry.get("fine") is not None
    assert any("invalid JSON" in m for messages in registry.errors().values() for m in messages)


def test_invalid_spec_is_reported_not_raised(user_dir):
    (user_dir / "bad.json").write_text(json.dumps({"schema_version": 1, "command": "bad",
                                                   "nonsense": True}))
    registry = HintRegistry(user_dir=str(user_dir))
    assert registry.get("bad") is None
    assert registry.errors()


def test_a_broken_spec_does_not_hide_the_bundled_ones(user_dir):
    (user_dir / "git.json").write_text("{{{")
    registry = HintRegistry(user_dir=str(user_dir))
    assert registry.get("git").origin == "bundled"


def test_missing_directory_is_fine():
    assert HintRegistry(user_dir="/nope/nothing/here").get("git") is not None


def test_reload_picks_up_a_new_spec(user_dir):
    registry = HintRegistry(user_dir=str(user_dir))
    assert registry.get("mytool") is None
    _write(user_dir, "mytool")
    assert registry.get("mytool") is None  # cached
    registry.reload()
    assert registry.get("mytool") is not None


def test_origin_and_path_are_recorded():
    spec = HintRegistry(user_dir="/nonexistent").get("git")
    assert spec.origin == "bundled"
    assert spec.source_path.endswith("git.json")


def test_every_provider_a_bundled_spec_names_exists():
    """A spec referring to a provider nobody registered would be silently
    dead: the source resolves to nothing and the user just sees no
    suggestions."""
    from zem.hints.providers import PROVIDERS
    from zem.hints.spec import AnyOfSource, ProviderSource

    def sources_of(node):
        for option in node.options:
            if option.value is not None:
                yield option.value
        for arg in node.args:
            yield arg.source
        for child in getattr(node, "subcommands", ()):
            yield from sources_of(child)

    def flatten(source):
        if isinstance(source, AnyOfSource):
            for nested in source.sources:
                yield from flatten(nested)
        else:
            yield source

    wanted = {
        source.name
        for spec in _unique(HintRegistry(user_dir="/nonexistent").load().values())
        for outer in sources_of(spec)
        for source in flatten(outer)
        if isinstance(source, ProviderSource)
    }
    assert wanted <= set(PROVIDERS.names()), sorted(wanted - set(PROVIDERS.names()))


def _unique(specs):
    """One entry per spec; aliases register the same object twice."""
    by_id = {id(spec): spec for spec in specs}
    return list(by_id.values())
