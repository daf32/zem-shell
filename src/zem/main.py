import logging
import os
import sys

from pydantic import ValidationError

USAGE = """\
zem — a modern shell for developers

Usage:
  zem                      Start an interactive shell
  zem -c COMMAND           Run COMMAND, then exit with its status
  zem FILE                 Run FILE as a script
  zem < FILE               Run a script read from standard input

Options:
  -c COMMAND     Command to run instead of starting a session
  --rc           Also read ~/.zemrc when running non-interactively
  -h, --help     Show this help
  -V, --version  Show the version

Environment:
  ZEM_CONFIG_PATH   Path to config.json
  ZEM_HINTS_PATH    Extra directories of completion hint specs
  ZEM_LOG_ENABLED   Set to "true" to log to stderr
  ZEM_LOG_LEVEL     DEBUG / INFO / WARNING / ERROR (default WARNING)
"""


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


class _Args:
    """What the command line asked for."""

    def __init__(self):
        self.command: str | None = None
        self.script: str | None = None
        self.read_stdin = False
        self.load_rc = False


def _parse_args(argv: list[str]) -> "_Args | int":
    """Parse `argv`; return an `_Args`, or an exit code if we are done."""
    args = _Args()
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("-V", "--version"):
            from zem import __version__

            print(f"zem {__version__}")
            return 0
        if arg in ("-h", "--help"):
            print(USAGE, end="")
            return 0
        if arg == "--rc":
            args.load_rc = True
        elif arg == "-c":
            index += 1
            if index >= len(argv):
                sys.stderr.write("zem: -c needs a command\n")
                return 2
            args.command = argv[index]
        elif arg == "--":
            index += 1
            break
        elif arg.startswith("-") and arg != "-":
            # Silently ignoring an unknown flag and opening a session
            # instead is how `zem --hepl` used to behave.
            sys.stderr.write(f"zem: unknown option '{arg}'\nTry 'zem --help'.\n")
            return 2
        else:
            args.script = arg
            index += 1
            break
        index += 1

    remaining = argv[index:]
    if remaining:
        sys.stderr.write(
            "zem: script arguments are not supported yet "
            f"(got {' '.join(remaining)})\n"
        )
        return 2
    if args.command is not None and args.script is not None:
        sys.stderr.write("zem: -c and a script file are mutually exclusive\n")
        return 2
    if args.command is None and args.script is None and not sys.stdin.isatty():
        # `echo 'ls' | zem`, like every other shell.
        args.read_stdin = True
    return args


def _run_non_interactive(args: _Args) -> int:
    """Run a command, a file or stdin without opening a session."""
    from zem.core.shell import Shell

    shell = Shell(headless=True, load_rc=args.load_rc)
    try:
        if args.command is not None:
            shell._run_script_lines(args.command.splitlines())
        elif args.script is not None:
            if not os.path.isfile(args.script):
                sys.stderr.write(f"zem: {args.script}: no such file\n")
                return 127
            shell._run_script_file(args.script)
        else:
            shell._run_script_lines(sys.stdin)
    except KeyboardInterrupt:
        return 130
    finally:
        shell.context.running = False

    # `exit 3` sets the status explicitly; otherwise the last command's
    # code is the script's, as in every other shell.
    if shell.context.exit_status:
        return shell.context.exit_status
    return shell.context.last_exit_code


def main(argv: "list[str] | None" = None) -> int:
    parsed = _parse_args(sys.argv[1:] if argv is None else argv)
    if isinstance(parsed, int):
        return parsed

    _configure_logging()
    try:
        if parsed.command is not None or parsed.script is not None or parsed.read_stdin:
            return _run_non_interactive(parsed)

        from zem.core.shell import Shell

        return Shell().run()
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
        return 1
    except Exception as e:
        from prompt_toolkit import HTML, print_formatted_text

        print_formatted_text(HTML(f"<ansired>[ERROR]</ansired> Failed to start shell: {e}"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
