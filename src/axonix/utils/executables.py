import os
from functools import lru_cache


@lru_cache(maxsize=8)
def _scan(path_value: str) -> tuple[str, ...]:
    commands = set()
    for directory in path_value.split(os.pathsep):
        if not os.path.isdir(directory):
            continue
        try:
            for entry in os.listdir(directory):
                full_path = os.path.join(directory, entry)
                if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                    commands.add(entry)
        except OSError:
            continue
    return tuple(sorted(commands))


def get_system_commands() -> list[str]:
    """Executable names on the current ``PATH``.

    Cached per distinct ``PATH`` value, so activating a venv or running
    `export PATH=...` is reflected immediately while repeated lookups for
    the same PATH stay cheap. Call :func:`refresh_system_commands` after
    installing new binaries into an existing directory.
    """
    return list(_scan(os.environ.get("PATH", "")))


def refresh_system_commands() -> None:
    _scan.cache_clear()
