import psh.builtins as builtins
import importlib
import pkgutil

def load_plugins():
    for module_info in pkgutil.iter_modules(builtins.__path__):
        if not module_info.ispkg:
            importlib.import_module(f"{builtins.__name__}.{module_info.name}")