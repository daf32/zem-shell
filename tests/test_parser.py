import pytest

from axonix.core.parser import Parser
from axonix.config.settings import AppConfig


def test_pipe_requires_command():
    cfg = AppConfig()
    parser = Parser("echo hi | ", {}, {}, cfg)
    with pytest.raises(Exception):
        parser.parse()


def test_quotes_and_variables():
    cfg = AppConfig()
    parser = Parser("echo \"hello $NAME\" 'raw $NAME'", {"NAME": "world"}, {}, cfg)
    cmds = parser.parse()
    assert cmds[0]["name"] == "echo"
    assert cmds[0]["args"] == ["hello world", "raw $NAME"]


def test_alias_expansion_single_pass():
    cfg = AppConfig()
    aliases = {"ll": "echo hi"}
    parser = Parser("ll", {}, aliases, cfg)
    cmds = parser.parse()
    assert cmds[0]["name"] == "echo"
    assert cmds[0]["args"] == ["hi"]


def test_redirections():
    cfg = AppConfig()
    parser = Parser("echo hello > out.txt", {}, {}, cfg)
    cmds = parser.parse()
    assert cmds[0]["name"] == "echo"
    assert cmds[0]["stdout_file"] == "out.txt"
    assert cmds[0]["append"] is False

    parser = Parser("cat < in.txt >> out.txt", {}, {}, cfg)
    cmds = parser.parse()
    assert cmds[0]["name"] == "cat"
    assert cmds[0]["stdin_file"] == "in.txt"
    assert cmds[0]["stdout_file"] == "out.txt"
    assert cmds[0]["append"] is True
