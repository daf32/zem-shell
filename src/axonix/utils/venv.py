"""
Simple venv utility for shell
"""
from pathlib import Path
import os


VENV_NAMES = (".venv", "venv", "env")

def find_venv(start: Path) -> Path | None:
    for directory in [start, *start.parents]:
        for name in VENV_NAMES:
            venv = directory / name
            if is_valid_venv(venv):
                return venv
    return None

def is_valid_venv(path: Path) -> bool:
    if not path.is_dir():
        return False
    
    if os.name == "nt":  # Windows
        return (path / "Scripts" / "python.exe").exists()
    else:  # Linux / macOS
        return (path / "bin" / "python").exists()

def activate_venv(context):
    """Activate venv - changes take effect only within this shell instance."""
    venv_path = find_venv(Path.cwd())
    if venv_path:
        if os.environ.get("VIRTUAL_ENV") == str(venv_path):
            return

        # Store original PATH before first activation
        if not hasattr(context, 'original_path') or not context.original_path:
            context.original_path = os.environ.get("PATH", "")

        if os.name == "nt":
            bin_path = venv_path / "Scripts"
        else:
            bin_path = venv_path / "bin"

        os.environ["VIRTUAL_ENV"] = str(venv_path)
        os.environ["PATH"] = str(bin_path) + os.pathsep + context.original_path

        context.active_venv = venv_path

def deactivate_venv(context):
    """Deactivate venv - changes take effect only within this shell instance."""
    # Remove VIRTUAL_ENV variable
    if "VIRTUAL_ENV" in os.environ:
        del os.environ["VIRTUAL_ENV"]
    
    # Restore original PATH if it was saved
    if hasattr(context, 'original_path') and context.original_path:
        os.environ["PATH"] = context.original_path
    
    context.active_venv = None

def get_venv_info() -> str | None:
    """
    Get the currently active virtual environment name
    """
    venv_path = os.environ.get("VIRTUAL_ENV")
    if not venv_path:
        return None
    
    venv_prompt = os.environ.get("VIRTUAL_ENV_PROMPT")
    if venv_prompt:
        return venv_prompt.strip("() ")
    
    return Path(venv_path).name