"""The plugin API.

A plugin is a Python package that declares a `zem.plugins` entry point
pointing at a `Plugin` subclass, or a single `.py` file in
`~/.zem/plugins`. See `docs/PLUGINS.md`.
"""

from zem.plugin.base import PLUGIN_API_VERSION, Plugin
from zem.plugin.manager import ENTRY_POINT_GROUP, LoadedPlugin, PluginManager

__all__ = [
    "ENTRY_POINT_GROUP",
    "PLUGIN_API_VERSION",
    "LoadedPlugin",
    "Plugin",
    "PluginManager",
]
