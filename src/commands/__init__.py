import src.commands as commands
import importlib
import pkgutil

def load_plugins():
    for module_info in pkgutil.iter_modules(commands.__path__):
        if not module_info.ispkg:
            importlib.import_module(f"{commands.__name__}.{module_info.name}")