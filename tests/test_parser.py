import pytest

from axonix.config.settings import AppConfig
from axonix.core.parser import Parser
from axonix.errors.parser_error import ParseError


def test_pipe_requires_command():
    cfg = AppConfig()
    parser = Parser("echo hi | ", {}, {}, cfg)
    with pytest.raises(ParseError):
        parser.parse()


def test_quotes_and_variables():
    cfg = AppConfig()
    parser = Parser("echo \"hello $NAME\" 'raw $NAME'", {"NAME": "world"}, {}, cfg)
    units = parser.parse()
    assert units[0]["pipeline"][0]["name"] == "echo"
    assert units[0]["pipeline"][0]["args"] == ["hello world", "raw $NAME"]


def test_alias_expansion_single_pass():
    cfg = AppConfig()
    aliases = {"ll": "echo hi"}
    parser = Parser("ll", {}, aliases, cfg)
    units = parser.parse()
    assert units[0]["pipeline"][0]["name"] == "echo"
    assert units[0]["pipeline"][0]["args"] == ["hi"]


def test_redirections():
    cfg = AppConfig()
    parser = Parser("echo hello > out.txt", {}, {}, cfg)
    units = parser.parse()
    cmd = units[0]["pipeline"][0]
    assert cmd["name"] == "echo"
    assert cmd["stdout_file"] == "out.txt"
    assert cmd["append"] is False

    parser = Parser("cat < in.txt >> out.txt", {}, {}, cfg)
    units = parser.parse()
    cmd = units[0]["pipeline"][0]
    assert cmd["name"] == "cat"
    assert cmd["stdin_file"] == "in.txt"
    assert cmd["stdout_file"] == "out.txt"
    assert cmd["append"] is True


def _args(line: str, variables=None) -> list[str]:
    cfg = AppConfig()
    units = Parser(line, variables or {}, {}, cfg).parse()
    cmd = units[0]["pipeline"][0]
    return [cmd["name"], *cmd["args"]]


def test_escaped_single_quote_outside_quotes():
    assert _args(r"echo a\'b") == ["echo", "a'b"]


def test_escaped_double_quote_inside_double_quotes():
    assert _args(r'echo "a\"b"') == ["echo", 'a"b']


def test_single_quote_splice_idiom():
    # 'it'\''s' is how re-sourceable listings embed a single quote.
    assert _args(r"echo 'it'\''s'") == ["echo", "it's"]


def test_escaped_dollar_is_literal():
    assert _args(r"echo \$HOME", {"HOME": "/h"}) == ["echo", "$HOME"]


def test_escaped_space_joins_token():
    assert _args(r"echo a\ b") == ["echo", "a b"]


def test_backslash_inside_single_quotes_is_literal():
    assert _args(r"echo 'a\b'") == ["echo", "a\\b"]
