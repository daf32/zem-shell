"""History expansion (`!!`, `!$`, `!N`, `!-N`, `!prefix`)."""

import pytest

from axonix.config.settings import AppConfig
from axonix.core.history_expand import HistoryExpansionError, expand_history

OPS = AppConfig().operators
HIST = ["echo one", "git status", "ls -la /tmp"]


@pytest.mark.parametrize("line, expected", [
    ("!!", "ls -la /tmp"),
    ("sudo !!", "sudo ls -la /tmp"),
    ("cat !$", "cat /tmp"),
    ("!1", "echo one"),
    ("!-2", "git status"),
    ("!git", "git status"),
    ("!ec x", "echo one x"),
    ("echo hi!", "echo hi!"),           # trailing ! is literal
    ("test a != b", "test a != b"),     # != is literal
    ("echo '!!'", "echo '!!'"),         # quoted
    ("echo \"!!\"", "echo \"!!\""),     # not expanded in double quotes either
    ("echo \\!!", "echo \\!!"),         # escaped
    ("echo a!!", "echo a!!"),           # not at word start
    ("! echo", "! echo"),               # ! followed by blank
])
def test_expand_history_table(line, expected):
    out, changed = expand_history(line, HIST, OPS)
    assert out == expected
    assert changed is (out != line)


@pytest.mark.parametrize("line", ["!9", "!-9", "!zzz", "!0"])
def test_unknown_event_raises(line):
    with pytest.raises(HistoryExpansionError, match="event not found"):
        expand_history(line, HIST, OPS)


def test_empty_history_raises():
    with pytest.raises(HistoryExpansionError):
        expand_history("!!", [], OPS)


def test_shell_execute_line_expands_when_recording(full_shell, capfd):
    full_shell._execute_line("echo first")
    capfd.readouterr()
    full_shell._execute_line("!!")
    out = capfd.readouterr().out
    assert out == "echo first\nfirst\n"          # echoed expansion, then output
    assert full_shell.context.history[-1] == "echo first"  # stored expanded


def test_shell_unknown_event_is_error_not_command(full_shell, capfd):
    full_shell._execute_line("!nope")
    assert full_shell.context.last_exit_code == 1
    assert "event not found" in capfd.readouterr().err


def test_expansion_can_be_disabled(full_shell, capfd):
    full_shell.config.history.expand = False
    full_shell._execute_line("echo !!")
    assert capfd.readouterr().out == "!!\n"
