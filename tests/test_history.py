from axonix.config.settings import AppConfig
from axonix.core.shell import Shell


def _shell_with_history_limit(tmp_path, limit: int) -> Shell:
    cfg = AppConfig(
        history={
            "enable": True,
            "file": str(tmp_path / "axonix_history_test"),
            "max_entries": limit,
            "load_on_start": False,
            "save_on_exit": False,
            "rotate": True,
        },
        rc={
            "auto_create": False,
            "file": str(tmp_path / "axonixrc_test"),
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
