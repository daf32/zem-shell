from axonix.core.shell import Shell
from axonix.config.settings import AppConfig


def make_shell_with_history_limit(limit: int = 3):
    cfg = AppConfig(
        settings={
            "history": {
                "enable": True,
                "file": "/tmp/axonix_history_test",
                "max_entries": limit,
                "load_on_start": False,
                "save_on_exit": False,
                "rotate": True,
            },
            "rc": {
                "auto_create": False,
                "file": "/tmp/axonixrc_test",
            },
        }
    )
    return Shell(config=cfg)


def test_history_trimmed_to_limit():
    shell = make_shell_with_history_limit(limit=2)
    shell._add_history("one")
    shell._add_history("two")
    shell._add_history("three")
    assert shell.context.history == ["two", "three"]
