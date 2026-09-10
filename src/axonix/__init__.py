import logging as _logging
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

# Default to a NullHandler so library use doesn't emit "No handlers found"
# warnings; `main.main()` opts into stderr output via `AXONIX_LOG_ENABLED`.
_logging.getLogger("axonix").addHandler(_logging.NullHandler())

try:
    # Single source of truth is `[project] version` in pyproject.toml.
    __version__ = _pkg_version("axonix")
except PackageNotFoundError:  # running from a plain checkout without install
    __version__ = "0.0.0+unknown"
