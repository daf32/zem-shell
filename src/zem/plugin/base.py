"""The `Plugin` class third-party packages subclass."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Mapping

if TYPE_CHECKING:
    from zem.builtins.base import BaseCommand
    from zem.ui.completers.base import BaseArgCompleter

#: Bumped when a hook's signature or meaning changes incompatibly. A plugin
#: declares the version it was written against; one from the future is
#: refused by name rather than half-loaded.
PLUGIN_API_VERSION = 1


class Plugin:
    """Base class for a Zem plugin.

    Subclass it, declare what you provide, and point an entry point at the
    class::

        [project.entry-points."zem.plugins"]
        weather = "zem_plugin_weather:WeatherPlugin"

    Every hook is optional and returns nothing by default. A hook that
    raises is reported and skipped: one broken plugin must not stop the
    shell from starting.
    """

    #: Shown by `plugin list`; defaults to the class name lowercased.
    name: str = ""
    version: str = "0.0.0"
    description: str = ""
    #: The API this plugin was written against.
    api_version: int = PLUGIN_API_VERSION

    # -- what the plugin provides -----------------------------------------

    def commands(self) -> Iterable[type["BaseCommand"]]:
        """Command classes to register (subclasses of `BaseCommand`)."""
        return ()

    def hint_specs(self) -> Iterable[str]:
        """Directories of completion hint specs (`*.json`)."""
        return ()

    def hint_providers(self) -> Mapping[str, Any]:
        """Named value providers, as `{"mytool.things": fn}`.

        Names must be namespaced; `zem.*` is reserved for the shell.
        """
        return {}

    def completers(self) -> Mapping[str, "BaseArgCompleter"]:
        """Python argument completers, as `{"command": completer}`.

        Only for what a hint spec cannot express — a spec is the usual way.
        """
        return {}

    def themes(self) -> Iterable[str]:
        """Directories of theme JSON files."""
        return ()

    # -- lifecycle ---------------------------------------------------------

    def on_startup(self, shell) -> None:
        """Called once, after the shell is built and before the first prompt."""

    def on_exit(self, shell) -> None:
        """Called once, while the shell is shutting down."""

    def pre_exec(self, line: str, shell) -> str | None:
        """Called with each line before it runs.

        Return a replacement to rewrite the line, or `None` to leave it
        alone. Keep it fast: this is on the path of every command.
        """
        return None

    def post_exec(self, line: str, exit_code: int, shell) -> None:
        """Called after each line, with the status it produced."""

    # -- housekeeping ------------------------------------------------------

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("name"):
            cls.name = cls.__name__.removesuffix("Plugin").lower() or cls.__name__.lower()

    def __repr__(self) -> str:
        return f"<{type(self).__name__}(name={self.name!r}, version={self.version!r})>"
