"""Shared pytest fixtures for axonix tests.

The shell normally requires a real TTY (it touches `termios`, installs
signal handlers, and constructs a `prompt_toolkit` `PromptSession`).
Under pytest `sys.stdin` is captured, so direct `Shell()` construction
fails. The `headless_shell` fixture wires up `Shell(..., headless=True)`,
which skips all of that while keeping `Parser`, `Executor`, builtins,
context, and config wiring intact.
"""

from __future__ import annotations

from typing import Callable, Optional

import pytest

from axonix.config.settings import AppConfig
from axonix.core.shell import Shell


def _isolated_config(tmp_path) -> AppConfig:
    """Build an AppConfig that won't touch the user's real history/rc."""
    return AppConfig(
        history={
            "enable": True,
            "file": str(tmp_path / "axonix_history"),
            "max_entries": 1000,
            "load_on_start": False,
            "save_on_exit": False,
            "rotate": True,
        },
        rc={
            "auto_create": False,
            "file": str(tmp_path / "axonixrc"),
        },
        venv={"auto": False},
    )


@pytest.fixture
def isolated_config(tmp_path) -> AppConfig:
    """Per-test AppConfig pointing at a tmp_path-owned history/rc."""
    return _isolated_config(tmp_path)


@pytest.fixture
def make_headless_shell(tmp_path, isolated_config) -> Callable[..., Shell]:
    """Factory that returns a fresh `Shell(headless=True)`.

    The factory accepts an optional `commands` dict (default: empty, so
    no plugins/builtins are auto-loaded — keeps tests fast and isolated).
    Pass `commands=None` to load the real registry.
    """
    def _factory(commands: Optional[dict] = None, config: Optional[AppConfig] = None) -> Shell:
        # Default: no commands at all. Tests that want builtins pass commands=None.
        if commands is None and config is None:
            return Shell(commands={}, config=isolated_config, headless=True)
        return Shell(
            commands=commands,
            config=config or isolated_config,
            headless=True,
        )

    return _factory


@pytest.fixture
def headless_shell(make_headless_shell) -> Shell:
    """Most tests just want `a` shell — give them one."""
    return make_headless_shell()


@pytest.fixture(autouse=True)
def _isolate_axonix_config(tmp_path, monkeypatch):
    """Point AXONIX_CONFIG_PATH at a per-test file so suite runs don't
    mutate the real `~/.config/axonix/config.json`."""
    cfg = tmp_path / "axonix-config.json"
    monkeypatch.setenv("AXONIX_CONFIG_PATH", str(cfg))
    # `settings.CONFIG_PATH` is computed at import time; override the
    # module attribute too in case anything has already imported it.
    import axonix.config.settings as s
    monkeypatch.setattr(s, "CONFIG_PATH", str(cfg))
    yield
