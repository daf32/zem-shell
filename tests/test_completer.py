"""AxonixCompleter: dispatch, fallback, quote-aware segments, isolation."""

import os
import stat

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from axonix.ui.completer import AxonixCompleter


def _complete(completer, text):
    doc = Document(text, len(text))
    return [c.text for c in completer.get_completions(doc, CompleteEvent())]


@pytest.fixture
def completer(full_shell):
    return AxonixCompleter(full_shell)


def test_command_position_lists_builtins_with_meta(completer):
    doc = Document("pw", 2)
    comps = list(completer.get_completions(doc, CompleteEvent()))
    texts = {c.text: c.display_meta_text for c in comps}
    assert texts.get("pwd") == "builtin"


def test_alias_completion_in_command_position(completer, full_shell):
    full_shell.context.aliases["gs"] = "git status"
    assert "gs" in _complete(completer, "g")


def test_git_subcommand_completion(completer):
    assert "checkout" in _complete(completer, "git ch")


def test_registered_completer_falls_back_to_paths(tmp_path, monkeypatch, completer):
    (tmp_path / "somefile.txt").write_text("")
    monkeypatch.chdir(tmp_path)
    # PathCompleter inserts the remainder of the word.
    assert "file.txt" in _complete(completer, "git add some")


def test_flag_words_do_not_fall_back_to_paths(tmp_path, monkeypatch, completer):
    (tmp_path / "-weird").write_text("")
    monkeypatch.chdir(tmp_path)
    assert _complete(completer, "git add -wei") == []


def test_alias_resolves_to_target_completer(completer, full_shell):
    full_shell.context.aliases["g"] = "git"
    assert "checkout" in _complete(completer, "g ch")


def test_pipe_inside_quotes_does_not_start_new_command(completer):
    # After a real pipe we are in command position; inside quotes we are
    # still completing arguments of `echo` (path fallback -> no "pwd").
    assert "pwd" in _complete(completer, 'echo "a | b" | pw')
    assert "pwd" not in _complete(completer, 'echo "a | pw')


def test_separators_and_logic_operators(completer):
    assert "pwd" in _complete(completer, "true && pw")
    assert "pwd" in _complete(completer, "true ; pw")
    assert "pwd" in _complete(completer, "false || pw")


def test_command_completer_registries_are_per_shell(full_shell, make_headless_shell):
    a = AxonixCompleter(full_shell)
    b = AxonixCompleter(make_headless_shell(commands=None))
    a.registry.register("zzz", a.registry.get("git"))
    assert b.registry.get("zzz") is None


def test_builtin_completer_overrides_default(completer):
    # `cd` provides its own DirectoryCompleter via get_completer().
    from axonix.ui.completers.defaults import DirectoryCompleter
    assert isinstance(completer.registry.get("cd"), DirectoryCompleter)
    assert completer.registry.get("yarn") is None  # npm flags were wrong for yarn


def test_system_commands_follow_path(tmp_path, monkeypatch, completer):
    exe = tmp_path / "axonix-test-binary"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert "axonix-test-binary" in _complete(completer, "axonix-test")
    monkeypatch.setenv("PATH", os.devnull)
    assert "axonix-test-binary" not in _complete(completer, "axonix-test")


def test_path_completion_for_arguments(tmp_path, monkeypatch, completer):
    (tmp_path / "somefile.txt").write_text("")
    (tmp_path / "subdir").mkdir()
    monkeypatch.chdir(tmp_path)
    assert "file.txt" in _complete(completer, "ls some")
    assert "file.txt" in _complete(completer, "cat a b some")
    assert _complete(completer, "cd sub") == ["dir"]       # dirs only for cd
    assert "file.txt" not in _complete(completer, "cd some")


def test_path_completion_inserts_only_the_remainder(tmp_path, monkeypatch, completer):
    (tmp_path / "somefile.txt").write_text("")
    monkeypatch.chdir(tmp_path)
    doc = Document("ls some", 7)
    comp = next(c for c in completer.get_completions(doc, CompleteEvent()))
    assert comp.text == "file.txt" and comp.start_position == 0
