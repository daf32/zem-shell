"""The `history` builtin (in-memory side; the file side needs a session)."""

import pytest

from axonix.ui.history import AxonixFileHistory


@pytest.fixture
def shell(full_shell):
    full_shell.context.history = ["echo one", "git status", "echo two"]
    return full_shell


def test_history_lists_all_numbered(shell, run):
    code, out, _ = run(shell, "history")
    assert code == 0
    assert out.splitlines() == ["    1  echo one", "    2  git status", "    3  echo two"]


def test_history_limit_and_pattern(shell, run):
    assert run(shell, "history 1")[1] == "    3  echo two\n"
    assert run(shell, "history GIT")[1] == "    2  git status\n"
    assert run(shell, "history 1 echo")[1] == "    3  echo two\n"


def test_history_delete(shell, run):
    assert run(shell, "history -d 2")[0] == 0
    assert shell.context.history == ["echo one", "echo two"]
    code, _, err = run(shell, "history -d 9")
    assert code == 1 and "out of range" in err


def test_history_clear_in_memory(shell, run):
    assert run(shell, "history -c")[0] == 0
    assert shell.context.history == []


def test_history_strict_args(shell, run):
    assert run(shell, "history --bogus")[0] == 2
    assert run(shell, "history -c extra")[0] == 2
    assert run(shell, "history -d x")[0] == 2
    assert run(shell, "history a b")[0] == 2


def test_file_history_clear_truncates_and_resets(tmp_path):
    path = tmp_path / "hist"
    h = AxonixFileHistory(str(path))
    h.append_string("one")
    h.append_string("two")
    assert list(h.load_history_strings()) == ["two", "one"]
    h.clear()
    assert path.read_bytes() == b""
    assert list(h.get_strings()) == []
    h.append_string("three")
    assert list(h.get_strings()) == ["three"]
