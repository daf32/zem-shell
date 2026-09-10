"""Shared pytest fixtures for zem tests.

The shell normally requires a real TTY (it touches `termios`, installs
signal handlers, and constructs a `prompt_toolkit` `PromptSession`).
Under pytest `sys.stdin` is captured, so direct `Shell()` construction
fails. The fixtures here wire up `Shell(..., headless=True)`, which skips
all of that while keeping `Parser`, `Executor`, builtins, context, and
config wiring intact.
"""

from __future__ import annotations

from typing import Callable, Optional

import pytest

from zem.builtins import load_plugins
from zem.builtins.registry import CommandRegistry
from zem.config.settings import AppConfig
from zem.core.shell import Shell


def _isolated_config(tmp_path) -> AppConfig:
    """Build an AppConfig that won't touch the user's real history/rc."""
    return AppConfig(
        history={
            "enable": True,
            "file": str(tmp_path / "zem_history"),
            "max_entries": 1000,
            "load_on_start": False,
            "save_on_exit": False,
            "rotate": True,
        },
        rc={
            "auto_create": False,
            "file": str(tmp_path / "zemrc"),
        },
        venv={"auto": False},
    )


@pytest.fixture
def isolated_config(tmp_path) -> AppConfig:
    """Per-test AppConfig pointing at a tmp_path-owned history/rc."""
    return _isolated_config(tmp_path)


@pytest.fixture
def make_headless_shell(isolated_config) -> Callable[..., Shell]:
    """Factory returning a fresh `Shell(headless=True)`.

    `commands` semantics:
      * omitted        -> empty command map (fast, no registry involved)
      * a dict         -> exactly those commands
      * `None`         -> load the real builtin registry (bundled plugins
                          included, user plugins excluded)
    """
    _EMPTY = object()

    def _factory(commands=_EMPTY, config: Optional[AppConfig] = None) -> Shell:
        if commands is _EMPTY:
            commands = {}
        return Shell(
            commands=commands,
            config=config or isolated_config,
            headless=True,
            user_plugins_dir=None,
        )

    return _factory


@pytest.fixture
def headless_shell(make_headless_shell) -> Shell:
    """A shell with no commands at all."""
    return make_headless_shell()


@pytest.fixture
def full_shell(make_headless_shell) -> Shell:
    """A headless shell with the real builtin registry loaded."""
    return make_headless_shell(commands=None)


@pytest.fixture
def run(capfd) -> Callable[[Shell, str], tuple[int, str, str]]:
    """Execute one line in `shell`; return `(exit_code, stdout, stderr)`.

    Captures at the file-descriptor level, so output from builtin worker
    threads and from external processes is both included. Redirected
    output lands in the target file as usual.
    """
    def _run(shell: Shell, line: str) -> tuple[int, str, str]:
        capfd.readouterr()  # drop anything buffered before this call
        shell._execute_line(line, add_to_history=False)
        captured = capfd.readouterr()
        return shell.context.last_exit_code, captured.out, captured.err

    return _run


@pytest.fixture(autouse=True)
def _isolate_zem_config(tmp_path, monkeypatch):
    """Point ZEM_CONFIG_PATH at a per-test file so suite runs don't
    mutate the real `~/.config/zem/config.json`."""
    cfg = tmp_path / "zem-config.json"
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(cfg))
    # `settings.CONFIG_PATH` is computed at import time; override the
    # module attribute too in case anything has already imported it.
    import zem.config.settings as s
    monkeypatch.setattr(s, "CONFIG_PATH", str(cfg))
    yield


@pytest.fixture(scope="session", autouse=True)
def _load_real_builtins_once():
    """Import the shipped builtins/plugins exactly once per session.

    Registration happens at import time, and Python won't re-import a
    module, so the registry must be populated *before* the per-test
    snapshot below is taken — otherwise the first restore would wipe the
    real builtins for good.
    """
    load_plugins(user_plugins_dir=None)


@pytest.fixture(autouse=True)
def _isolate_command_registry():
    """Snapshot/restore the global `CommandRegistry`.

    `BaseCommand.__init_subclass__` registers every subclass process-wide,
    so a test-local builtin defined in one module would otherwise show up
    in every later test that loads the real registry.
    """
    classes = dict(CommandRegistry._command_classes)
    instances = dict(CommandRegistry._commands)
    # Test modules define throwaway builtins at import (collection) time,
    # before this fixture ever runs; hide anything not shipped by zem.
    for name, cls in classes.items():
        if not cls.__module__.startswith("zem."):
            CommandRegistry._command_classes.pop(name, None)
            CommandRegistry._commands.pop(name, None)
    yield
    CommandRegistry._command_classes.clear()
    CommandRegistry._command_classes.update(classes)
    CommandRegistry._commands.clear()
    CommandRegistry._commands.update(instances)
