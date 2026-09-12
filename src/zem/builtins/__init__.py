import zem.themes  # noqa: F401  -- keeps the theme data importable from the package
from zem.plugin.manager import DEFAULT_USER_PLUGINS_DIR, PluginManager

__all__ = ["DEFAULT_USER_PLUGINS_DIR", "load_plugins"]


def load_plugins(
    user_plugins_dir: str | None = DEFAULT_USER_PLUGINS_DIR,
    disabled: "frozenset[str] | None" = None,
) -> PluginManager:
    """Discover builtins, bundled plugins and the user's own.

    ``user_plugins_dir`` defaults to ``~/.zem/plugins``; pass ``None`` to
    skip user plugins entirely (tests do this so a developer's personal
    plugins never leak into the suite).

    Returns the `PluginManager`, which holds what was found and what went
    wrong. Commands still register themselves at import time, so callers
    that only want those can ignore the return value.
    """
    manager = PluginManager(
        user_plugins_dir=user_plugins_dir,
        disabled=disabled or frozenset(),
    )
    manager.discover()
    manager.register_commands()
    manager.register_hint_providers()
    return manager
