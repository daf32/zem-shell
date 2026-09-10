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
