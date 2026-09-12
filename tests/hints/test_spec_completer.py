"""SpecCompleter: from a spec plus a line to actual completions."""

import pytest
from prompt_toolkit.document import Document

from zem.hints.completer import SpecCompleter
from zem.hints.providers import PROVIDERS
from zem.hints.spec import parse_spec

SPEC = {
    "schema_version": 1,
    "command": "demo",
    "fallback": "files",
    "subcommands": [
        {
            "name": "run",
            "description": "Run it",
            "options": [
                {"names": ["-f", "--fast"], "description": "Quick"},
                {"names": ["--mode"], "value": {"type": "values", "items": ["dev", "prod"]}},
            ],
            "args": [{"name": "branch", "source": {"type": "provider", "name": "test.branches"}}],
        },
        {"name": "stop", "description": "Stop it", "args": [
            {"name": "where", "source": {"type": "none"}},
        ]},
    ],
}


@pytest.fixture
def completer(full_shell):
    PROVIDERS.register(
        "test.branches",
        lambda ctx: [("main", "trunk"), ("my branch", "spaces")],
        override=True,
    )
    return SpecCompleter(parse_spec(SPEC), full_shell)


def _complete(completer, line):
    """Split `line` the way ZemCompleter would and complete it."""
    parts = line.split()
    word = "" if line.endswith(" ") else (parts[-1] if parts else "")
    return list(completer.get_completions(Document(line, len(line)), parts, word))


def _texts(completer, line):
    return [c.text for c in _complete(completer, line)]


def test_subcommands_with_descriptions(completer):
    found = {c.text: c.display_meta_text for c in _complete(completer, "demo ")}
    assert found == {"run": "Run it", "stop": "Stop it"}


def test_subcommand_prefix_filters(completer):
    assert _texts(completer, "demo ru") == ["run"]


def test_flags_after_a_dash(completer):
    assert _texts(completer, "demo run -") == ["-f", "--fast", "--mode"]


def test_flag_prefix_with_dashes(completer):
    # The regression that made every flag branch dead code.
    assert _texts(completer, "demo run --fa") == ["--fast"]


def test_flag_replaces_the_whole_word(completer):
    comp = _complete(completer, "demo run --fa")[0]
    assert comp.start_position == -4


def test_flag_value(completer):
    assert _texts(completer, "demo run --mode ") == ["dev", "prod"]


def test_inline_flag_value_replaces_only_the_value(completer):
    comp = _complete(completer, "demo run --mode=d")[0]
    assert comp.text == "dev" and comp.start_position == -1


def test_values_from_a_provider(completer):
    assert "main" in _texts(completer, "demo run ")


def test_values_needing_quotes_are_quoted(completer):
    quoted = [c for c in _complete(completer, "demo run ") if c.display_text == "my branch"]
    assert quoted[0].text == "'my branch'"


def test_none_source_offers_nothing(completer):
    assert _texts(completer, "demo stop ") == []


def test_unknown_subcommand_falls_back_to_paths(tmp_path, monkeypatch, completer):
    # We have no idea what `nope` takes, so behave like a shell with no
    # completion at all rather than inventing arguments.
    (tmp_path / "somefile.txt").write_text("")
    monkeypatch.chdir(tmp_path)
    assert _texts(completer, "demo nope some") == ["file.txt"]


def test_fallback_to_files_for_an_undescribed_position(tmp_path, monkeypatch, completer):
    (tmp_path / "somefile.txt").write_text("")
    monkeypatch.chdir(tmp_path)
    assert "file.txt" in _texts(completer, "demo run main some")


def test_files_source(tmp_path, monkeypatch, full_shell):
    (tmp_path / "somefile.txt").write_text("")
    (tmp_path / "subdir").mkdir()
    monkeypatch.chdir(tmp_path)
    spec = parse_spec({"schema_version": 1, "command": "demo",
                       "args": [{"name": "f", "source": {"type": "files"}}]})
    assert "file.txt" in _texts(SpecCompleter(spec, full_shell), "demo some")


def test_dirs_source_excludes_files(tmp_path, monkeypatch, full_shell):
    (tmp_path / "somefile.txt").write_text("")
    (tmp_path / "somedir").mkdir()
    monkeypatch.chdir(tmp_path)
    spec = parse_spec({"schema_version": 1, "command": "demo",
                       "args": [{"name": "d", "source": {"type": "dirs"}}]})
    assert _texts(SpecCompleter(spec, full_shell), "demo some") == ["dir"]


def test_any_of_merges_sources(tmp_path, monkeypatch, full_shell):
    (tmp_path / "mainfile.txt").write_text("")
    monkeypatch.chdir(tmp_path)
    PROVIDERS.register("test.branches", lambda ctx: ["main"], override=True)
    spec = parse_spec({"schema_version": 1, "command": "demo", "args": [{
        "name": "t",
        "source": {"type": "any_of", "sources": [
            {"type": "provider", "name": "test.branches"},
            {"type": "files"},
        ]},
    }]})
    assert _texts(SpecCompleter(spec, full_shell), "demo main") == ["main", "file.txt"]


def test_dynamic_switch_silences_providers(full_shell, completer):
    full_shell.config.hints.dynamic = False
    assert _texts(completer, "demo run ") == []
    # Static parts keep working.
    assert _texts(completer, "demo ") == ["run", "stop"]
