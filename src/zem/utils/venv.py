"""
Simple venv utility for shell
"""
import os
from pathlib import Path

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


def activate_venv(context, venv_path: Path | None = None) -> Path | None:
    """Activate ``venv_path`` (or the nearest venv found from cwd).

    Returns the activated path, or ``None`` if nothing was found. Changes
    go through the context's variable API so children see the new PATH.
    """
    if venv_path is None:
        venv_path = find_venv(Path.cwd())
    if venv_path is None:
        return None

    if context.variables.get("VIRTUAL_ENV") == str(venv_path):
        return venv_path

    # Remember the pre-venv PATH so deactivate can restore it.
    if not context.original_path:
        context.original_path = context.variables.get("PATH", "")

    bin_path = venv_path / ("Scripts" if os.name == "nt" else "bin")

    context.set_var("VIRTUAL_ENV", str(venv_path), export=True)
    context.set_var("PATH", str(bin_path) + os.pathsep + context.original_path, export=True)
    context.active_venv = str(venv_path)
    return venv_path


def deactivate_venv(context) -> bool:
    """Deactivate the current venv. Returns ``False`` if none was active."""
    if "VIRTUAL_ENV" not in context.variables:
        return False

    context.unset_var("VIRTUAL_ENV")
    if context.original_path:
        context.set_var("PATH", context.original_path, export=True)
    context.active_venv = None
    return True


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
