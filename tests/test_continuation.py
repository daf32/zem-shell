"""Line continuation detection and script-line joining."""

import pytest

from zem.config.settings import AppConfig
from zem.core.parser import Parser
from zem.core.scan import join_lines

OPS = AppConfig().operators


@pytest.mark.parametrize("text, expected", [
    ("echo a", False),
    ("echo a \\", True),
    ("echo a \\\\", False),          # escaped backslash is literal
    ("echo 'a", True),
    ("echo \"a", True),
    ("echo 'a\\'", False),           # backslash is literal in single quotes
    ("echo $(ls", True),
    ("echo $(ls)", False),
    ("a |", True),
    ("a ||", True),
    ("a &&", True),
    ("a &", False),                  # background, not continuation
    ("echo '|'", False),
    ("echo a\\|", False),            # escaped pipe is text
    ("echo '&&'", False),
    ("", False),
    ("   ", False),
])
def test_needs_continuation(text, expected):
    assert Parser.needs_continuation(text, AppConfig()) is expected


def test_join_lines_backslash_glues_directly():
    assert join_lines("echo a \\", "b", OPS) == "echo a b"


def test_join_lines_quote_keeps_newline():
    assert join_lines("echo 'a", "b'", OPS) == "echo 'a\nb'"


def test_join_lines_after_operator_keeps_newline():
    assert join_lines("a |", "b", OPS) == "a |\nb"


def test_run_script_lines_joins_continuations(full_shell, run, capfd):
    lines = [
        "# comment",
        "",
        "echo one \\",
        "  two",
        "echo 'multi",
        "line'",
        "echo a |",
        "cat",
        "echo done",
    ]
    capfd.readouterr()
    code = full_shell._run_script_lines(lines)
    out = capfd.readouterr().out
    assert code == 0
    assert out == "one two\nmulti\nline\na\ndone\n"


def test_run_script_lines_continues_past_errors(full_shell, capfd):
    code = full_shell._run_script_lines(["nope-cmd-xyz", "echo after"])
    captured = capfd.readouterr()
    assert "after" in captured.out
    assert "Unknown command" in captured.err
    assert code == 0  # last line succeeded


def test_run_script_file_missing(full_shell, capfd):
    assert full_shell._run_script_file("/nonexistent/rc") == 1
    assert "No such file" in capfd.readouterr().err


def test_rc_file_supports_continuation(tmp_path, make_headless_shell, isolated_config, capfd):
    rc = tmp_path / "zemrc"
    rc.write_text("echo one \\\n  two\nalias hi='echo hi'\nhi\n")
    isolated_config.rc.file = str(rc)
    shell = make_headless_shell(commands=None, config=isolated_config)
    assert shell.context.aliases["hi"] == "echo hi"
    assert capfd.readouterr().out == "one two\nhi\n"
