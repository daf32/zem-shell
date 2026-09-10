"""AxonixLexer: command validity follows PATH; path cache can be cleared."""

import stat

import pytest
from prompt_toolkit.document import Document

from axonix.ui.lexer import AxonixLexer


def _tokens(lexer, text):
    return lexer.lex_document(Document(text))(0)


def _style_of(lexer, text, word):
    return next(style for style, tok in _tokens(lexer, text) if tok == word)


@pytest.fixture
def lexer(full_shell):
    return AxonixLexer(full_shell)


def test_builtin_alias_and_unknown(lexer, full_shell):
    assert _style_of(lexer, "pwd", "pwd") == "class:command"
    full_shell.context.aliases["ll"] = "ls"
    assert _style_of(lexer, "ll", "ll") == "class:command"
    assert _style_of(lexer, "nope-cmd-xyz", "nope-cmd-xyz") == "class:error"


def test_command_validity_follows_path_changes(tmp_path, monkeypatch, lexer):
    exe = tmp_path / "freshbin"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "/nonexistent")
    assert _style_of(lexer, "freshbin", "freshbin") == "class:error"
    monkeypatch.setenv("PATH", str(tmp_path))   # e.g. venv activate / export PATH
    assert _style_of(lexer, "freshbin", "freshbin") == "class:command"


def test_path_not_found_cache_is_clearable(tmp_path, monkeypatch, lexer):
    monkeypatch.chdir(tmp_path)
    target = "./later.txt"
    assert _style_of(lexer, f"cat {target}", target) == "class:path-notfound"
    (tmp_path / "later.txt").write_text("")
    assert _style_of(lexer, f"cat {target}", target) == "class:path-notfound"  # cached
    lexer.clear_path_cache()
    assert _style_of(lexer, f"cat {target}", target) == "class:path"


def test_operators_and_strings(lexer):
    tokens = _tokens(lexer, "echo 'x' | cat")
    assert ("class:operator", "|") in tokens
    assert any(style == "class:string" for style, _ in tokens)
