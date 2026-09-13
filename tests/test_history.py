from zem.config.settings import AppConfig
from zem.core.shell import Shell


def _shell_with_history_limit(tmp_path, limit: int) -> Shell:
    cfg = AppConfig(
        history={
            "enable": True,
            "file": str(tmp_path / "zem_history_test"),
            "max_entries": limit,
            "load_on_start": False,
            "save_on_exit": False,
            "rotate": True,
        },
        rc={
            "auto_create": False,
            "file": str(tmp_path / "zemrc_test"),
        },
        venv={"auto": False},
    )
    return Shell(commands={}, config=cfg, headless=True)


def test_history_trimmed_to_limit(tmp_path):
    shell = _shell_with_history_limit(tmp_path, limit=2)
    shell._add_history("one")
    shell._add_history("two")
    shell._add_history("three")
    assert shell.context.history == ["two", "three"]


# -- the history file -------------------------------------------------------

from zem.ui.history import ZemFileHistory  # noqa: E402


def test_history_file_is_created_private(tmp_path):
    path = tmp_path / "hist"
    ZemFileHistory(str(path))
    assert path.exists()
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_entries_are_oldest_first_and_survive_reopening(tmp_path):
    path = str(tmp_path / "hist")
    h = ZemFileHistory(path)
    h.append_string("one")
    h.append_string("two\nlines")
    assert ZemFileHistory(path).entries() == ["one", "two\nlines"]


def test_load_false_starts_empty_but_still_appends(tmp_path):
    path = str(tmp_path / "hist")
    ZemFileHistory(path).append_string("old")
    h = ZemFileHistory(path, load=False)
    assert list(h.load_history_strings()) == []
    h.append_string("new")
    assert ZemFileHistory(path).entries() == ["old", "new"]


def test_persist_false_keeps_the_file_untouched(tmp_path):
    path = tmp_path / "hist"
    h = ZemFileHistory(str(path), persist=False)
    h.append_string("secret")
    assert not path.exists()
    assert h.get_strings() == ["secret"]  # arrows still see it this session


def test_rotate_keeps_the_last_entries(tmp_path):
    path = str(tmp_path / "hist")
    h = ZemFileHistory(path)
    for n in range(5):
        h.append_string(f"cmd {n}")
    h.rotate(2)
    assert ZemFileHistory(path).entries() == ["cmd 3", "cmd 4"]
    h.rotate(10)  # nothing to trim: file left alone
    assert ZemFileHistory(path).entries() == ["cmd 3", "cmd 4"]


def test_shell_seeds_memory_from_the_file(tmp_path):
    shell = _shell_with_history_limit(tmp_path, limit=2)
    path = shell.config.history.file
    h = ZemFileHistory(path)
    for n in range(3):
        h.append_string(f"cmd {n}")
    shell.config.history.load_on_start = True
    shell._setup_history()
    assert shell.context.history == ["cmd 1", "cmd 2"]
    assert shell.file_history is not None


def test_shell_does_not_read_the_file_when_load_on_start_is_off(tmp_path):
    shell = _shell_with_history_limit(tmp_path, limit=5)
    ZemFileHistory(shell.config.history.file).append_string("old")
    shell._setup_history()
    assert shell.context.history == []


def test_close_rotates_the_file_once(tmp_path, monkeypatch):
    shell = _shell_with_history_limit(tmp_path, limit=2)
    shell.config.history.save_on_exit = True
    shell._setup_history()
    for n in range(4):
        shell.file_history.append_string(f"cmd {n}")
    calls = []
    monkeypatch.setattr(shell.plugins, "notify", lambda hook, *a: calls.append(hook))
    shell._close_shell()
    shell._close_shell()  # SIGTERM handler + run()'s finally: still once
    assert calls == ["on_exit"]
    assert ZemFileHistory(shell.config.history.file).entries() == ["cmd 2", "cmd 3"]
