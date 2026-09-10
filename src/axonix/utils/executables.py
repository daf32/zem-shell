import os


def get_system_commands():
    """Get all executable files in system PATH."""
    paths = os.environ.get("PATH", "").split(os.pathsep)
    commands = set()
    for path in paths:
        if os.path.isdir(path):
            try:
                for entry in os.listdir(path):
                    full_path = os.path.join(path, entry)
                    if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                        commands.add(entry)
            except OSError:
                continue
    return sorted(list(commands))
