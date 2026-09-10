import os
import sys
import axonix.builtins as builtins
import axonix.themes
import axonix.plugins
import importlib
import pkgutil

DEFAULT_USER_PLUGINS_DIR = os.path.expanduser("~/.axonix/plugins")


def load_plugins(user_plugins_dir: str | None = DEFAULT_USER_PLUGINS_DIR):
    """Import builtins, bundled plugins, then user plugins.

    ``user_plugins_dir`` defaults to ``~/.axonix/plugins``; pass ``None`` to
    skip user plugins entirely (tests do this so a developer's personal
    plugins never leak into the suite).
    """
    # Load built-in commands
    for module_info in pkgutil.iter_modules(builtins.__path__):
        if not module_info.ispkg:
            importlib.import_module(f"{builtins.__name__}.{module_info.name}")

    # Load internal plugins (bundled with axonix)
    for module_info in pkgutil.iter_modules(axonix.plugins.__path__):
        if not module_info.ispkg:
            importlib.import_module(f"axonix.plugins.{module_info.name}")
    
    # Load external plugins from ~/.axonix/plugins
    plugins_dir = user_plugins_dir
    if plugins_dir and os.path.exists(plugins_dir):
        if plugins_dir not in sys.path:
            sys.path.append(plugins_dir)
            
        for module_info in pkgutil.iter_modules([plugins_dir]):
            if not module_info.ispkg:
                try:
                    importlib.import_module(module_info.name)
                except Exception as e:
                    print(f"Error loading external plugin '{module_info.name}': {e}")