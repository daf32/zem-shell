import logging
import os
import sys
from pydantic import ValidationError


def _configure_logging():
    """Wire `axonix.*` loggers up to stderr when AXONIX_LOG_ENABLED=true.

    Levels come from AXONIX_LOG_LEVEL (DEBUG/INFO/WARNING/ERROR), default
    WARNING. When disabled, the NullHandler installed in ``axonix/__init__``
    swallows everything.
    """
    if os.getenv("AXONIX_LOG_ENABLED", "").lower() != "true":
        return
    level_name = os.getenv("AXONIX_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    pkg_logger = logging.getLogger("axonix")
    pkg_logger.addHandler(handler)
    pkg_logger.setLevel(level)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--version", "-V"):
        from axonix import __version__
        print(f"axonix {__version__}")
        return
    _configure_logging()
    try:
        from axonix.core.shell import Shell
        shell = Shell()
        shell.run()
    except ValidationError as e:
        from prompt_toolkit import print_formatted_text, HTML
        from axonix.utils.colors import error_tag
        from axonix.config.settings import AppConfig
        
        config = AppConfig()
        print_formatted_text(HTML(f"{error_tag(config)} Configuration Error:"))
        for error in e.errors():
            loc = ".".join(str(x) for x in error['loc'])
            print_formatted_text(HTML(f"  <ansiyellow>-</ansiyellow> <ansicyan>{loc}</ansicyan>: {error['msg']}"))
        sys.exit(1)
    except Exception as e:
        from prompt_toolkit import print_formatted_text, HTML
        from axonix.utils.colors import error_tag
        from axonix.config.settings import AppConfig
        
        config = AppConfig()
        print_formatted_text(HTML(f"{error_tag(config)} Failed to start shell: {e}"))
        sys.exit(1)

if __name__ == "__main__":
    main()
