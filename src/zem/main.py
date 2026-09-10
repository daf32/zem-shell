import logging
import os
import sys

from pydantic import ValidationError


def _configure_logging():
    """Wire `zem.*` loggers up to stderr when ZEM_LOG_ENABLED=true.

    Levels come from ZEM_LOG_LEVEL (DEBUG/INFO/WARNING/ERROR), default
    WARNING. When disabled, the NullHandler installed in ``zem/__init__``
    swallows everything.
    """
    if os.getenv("ZEM_LOG_ENABLED", "").lower() != "true":
        return
    level_name = os.getenv("ZEM_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    pkg_logger = logging.getLogger("zem")
    pkg_logger.addHandler(handler)
    pkg_logger.setLevel(level)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        from zem import __version__
        print(f"zem {__version__}")
        return
    _configure_logging()
    try:
        from zem.core.shell import Shell
        shell = Shell()
        sys.exit(shell.run())
    except ValidationError as e:
        from prompt_toolkit import HTML, print_formatted_text

        # Don't construct AppConfig() here: the config is what's broken.
        from zem.config.settings import format_validation_error, get_config_path

        print_formatted_text(HTML("<ansired>[ERROR]</ansired> Configuration Error:"))
        for line in format_validation_error(e):
            loc, _, msg = line.partition(": ")
            print_formatted_text(
                HTML(f"  <ansiyellow>-</ansiyellow> <ansicyan>{loc}</ansicyan>: {msg}")
            )
        print_formatted_text(HTML(f"  in <ansicyan>{get_config_path()}</ansicyan>"))
        sys.exit(1)
    except Exception as e:
        from prompt_toolkit import HTML, print_formatted_text

        print_formatted_text(HTML(f"<ansired>[ERROR]</ansired> Failed to start shell: {e}"))
        sys.exit(1)

if __name__ == "__main__":
    main()
