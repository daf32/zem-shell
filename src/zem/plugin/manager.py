"""Finding, loading and wiring up plugins."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import inspect
import logging
import os
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Iterable, Optional

from zem.plugin.base import PLUGIN_API_VERSION, Plugin

log = logging.getLogger(__name__)

#: Packages advertise themselves here:
#:     [project.entry-points."zem.plugins"]
#:     weather = "zem_plugin_weather:WeatherPlugin"
ENTRY_POINT_GROUP = "zem.plugins"

DEFAULT_USER_PLUGINS_DIR = os.path.expanduser("~/.zem/plugins")


@dataclass
class LoadedPlugin:
    """A plugin that was found, and how it went."""

    name: str
    plugin: Optional[Plugin]
    origin: str  # "bundled" | "entry_point" | "user"
    source: str
    enabled: bool = True
    error: str = ""

    @property
    def version(self) -> str:
        return getattr(self.plugin, "version", "") if self.plugin else ""

    @property
    def description(self) -> str:
        return getattr(self.plugin, "description", "") if self.plugin else ""


@dataclass
class PluginManager:
    """Discovers plugins and hands the shell what they provide.

    Three sources, weakest first: the plugins bundled with Zem, packages
    that declare a `zem.plugins` entry point, and single files in
    `~/.zem/plugins`. A later one may reuse a name to replace an earlier.
    """

    user_plugins_dir: Optional[str] = DEFAULT_USER_PLUGINS_DIR
    disabled: frozenset = field(default_factory=frozenset)
    loaded: list[LoadedPlugin] = field(default_factory=list)

    def discover(self) -> list[LoadedPlugin]:
        """Find every plugin. Never raises: a broken one is recorded."""
        self.loaded = []
        self._load_bundled()
        self._load_entry_points()
        self._load_user_dir()
        return self.loaded

    # -- sources -----------------------------------------------------------

    def _load_bundled(self) -> None:
        """Import the builtins, then the plugins shipped with Zem.

        Builtins are not plugins: they are the shell, they cannot be
        disabled, and they do not appear in `plugin list`. The modules in
        `zem.plugins` do appear, so that a user can see and switch off what
        ships with the shell.
        """
        import zem.builtins as builtins_pkg
        import zem.plugins as bundled_pkg

        for module_info in pkgutil.iter_modules(builtins_pkg.__path__):
            if not module_info.ispkg:
                importlib.import_module(f"{builtins_pkg.__name__}.{module_info.name}")

        for module_info in pkgutil.iter_modules(bundled_pkg.__path__):
            if module_info.ispkg:
                continue
            record = LoadedPlugin(
                name=module_info.name, plugin=None, origin="bundled",
                source=f"{bundled_pkg.__name__}.{module_info.name}",
            )
            if module_info.name in self.disabled:
                # Not importing it is the only way to disable it: commands
                # register themselves at import time.
                record.enabled = False
                self.loaded.append(record)
                continue
            try:
                module = importlib.import_module(f"{bundled_pkg.__name__}.{module_info.name}")
            except Exception as exc:
                record.error = f"{type(exc).__name__}: {exc}"
                log.warning("bundled plugin %r failed: %s", module_info.name, exc)
                self._accept(record)
                continue
            found = self._plugin_class_in(module)
            if found is not None:
                try:
                    record.plugin = self._instantiate(found)
                except Exception as exc:
                    record.error = f"{type(exc).__name__}: {exc}"
            self._accept(record)

    def _load_entry_points(self) -> None:
        try:
            entry_points = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
        except Exception as exc:  # a broken installed distribution
            log.warning("could not read %s entry points: %s", ENTRY_POINT_GROUP, exc)
            return

        for entry_point in entry_points:
            record = LoadedPlugin(
                name=entry_point.name, plugin=None, origin="entry_point",
                source=getattr(entry_point, "value", ""),
            )
            if entry_point.name in self.disabled:
                record.enabled = False
                self.loaded.append(record)
                continue
            try:
                record.plugin = self._instantiate(entry_point.load())
            except Exception as exc:
                record.error = f"{type(exc).__name__}: {exc}"
                log.warning("plugin %r failed to load: %s", entry_point.name, exc)
            self._accept(record)

    def _load_user_dir(self) -> None:
        directory = self.user_plugins_dir
        if not directory or not os.path.isdir(directory):
            return
        if directory not in sys.path:
            sys.path.append(directory)

        for module_info in pkgutil.iter_modules([directory]):
            if module_info.ispkg:
                continue
            record = LoadedPlugin(
                name=module_info.name, plugin=None, origin="user",
                source=os.path.join(directory, f"{module_info.name}.py"),
            )
            if module_info.name in self.disabled:
                record.enabled = False
                self.loaded.append(record)
                continue
            try:
                module = importlib.import_module(module_info.name)
            except Exception as exc:
                record.error = f"{type(exc).__name__}: {exc}"
                log.warning("plugin %r failed to import: %s", module_info.name, exc)
                self._accept(record)
                continue
            # A single-file plugin may define a Plugin subclass, or it may
            # be the old style: a module that just declares commands, which
            # registered themselves on import. Both keep working.
            found = self._plugin_class_in(module)
            if found is not None:
                try:
                    record.plugin = self._instantiate(found)
                except Exception as exc:
                    record.error = f"{type(exc).__name__}: {exc}"
            self._accept(record)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _plugin_class_in(module) -> Optional[type]:
        for value in vars(module).values():
            if inspect.isclass(value) and issubclass(value, Plugin) and value is not Plugin:
                return value
        return None

    @staticmethod
    def _instantiate(target) -> Plugin:
        plugin = target() if inspect.isclass(target) else target
        if not isinstance(plugin, Plugin):
            raise TypeError(f"{target!r} is not a zem Plugin")
        if plugin.api_version > PLUGIN_API_VERSION:
            raise RuntimeError(
                f"needs plugin API {plugin.api_version}, this zem provides "
                f"{PLUGIN_API_VERSION} — upgrade zem"
            )
        return plugin

    def _accept(self, record: LoadedPlugin) -> None:
        # A later source replaces an earlier one of the same name.
        self.loaded = [p for p in self.loaded if p.name != record.name]
        self.loaded.append(record)

    # -- what the plugins provide -----------------------------------------

    def active(self) -> Iterable[Plugin]:
        for record in self.loaded:
            if record.enabled and record.plugin is not None and not record.error:
                yield record.plugin

    def _collect(self, hook: str, sink):
        """Call `hook` on every active plugin, surviving a broken one."""
        for record in self.loaded:
            if not record.enabled or record.plugin is None or record.error:
                continue
            try:
                sink(record, getattr(record.plugin, hook)())
            except Exception as exc:
                record.error = f"{hook}(): {type(exc).__name__}: {exc}"
                log.warning("plugin %r failed in %s(): %s", record.name, hook, exc)

    def register_commands(self) -> None:
        from zem.builtins.registry import CommandRegistry

        def sink(record, commands):
            for command_class in commands:
                CommandRegistry.register(command_class)

        self._collect("commands", sink)

    def register_hint_providers(self) -> None:
        from zem.hints.providers import PROVIDERS

        def sink(record, providers):
            for name, fn in dict(providers).items():
                PROVIDERS.register(name, fn, override=True)

        self._collect("hint_providers", sink)

    def hint_spec_dirs(self) -> list[str]:
        directories: list[str] = []
        self._collect("hint_specs", lambda record, paths: directories.extend(paths))
        return directories

    def theme_dirs(self) -> list[str]:
        directories: list[str] = []
        self._collect("themes", lambda record, paths: directories.extend(paths))
        return directories

    def completers(self) -> dict:
        found: dict = {}
        self._collect("completers", lambda record, mapping: found.update(dict(mapping)))
        return found

    # -- lifecycle ---------------------------------------------------------

    def notify(self, hook: str, *args) -> None:
        """Call a lifecycle hook on every active plugin."""
        for record in self.loaded:
            if not record.enabled or record.plugin is None or record.error:
                continue
            try:
                getattr(record.plugin, hook)(*args)
            except Exception as exc:
                log.warning("plugin %r failed in %s: %s", record.name, hook, exc)

    def rewrite_line(self, line: str, shell) -> str:
        """Run `pre_exec` hooks; the first rewrite wins."""
        for record in self.loaded:
            if not record.enabled or record.plugin is None or record.error:
                continue
            try:
                replacement = record.plugin.pre_exec(line, shell)
            except Exception as exc:
                log.warning("plugin %r failed in pre_exec: %s", record.name, exc)
                continue
            if isinstance(replacement, str) and replacement != line:
                return replacement
        return line
