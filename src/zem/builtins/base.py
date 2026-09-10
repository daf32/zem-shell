import inspect
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, TextIO

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext
    from zem.ui.completers.base import BaseArgCompleter


class BaseCommand:
    """Base class for all shell builtin commands.
    
    Subclasses must implement the `execute` method. Command name is automatically
    determined from the class file name if not explicitly set. Commands are 
    automatically registered with CommandRegistry upon subclass creation.
    
    Attributes:
        name: Command name (auto-determined from filename if empty)
        help: Command description
        usage: Command usage syntax
        tags: Command classification tags (default: ["builtin"])
        examples: Example invocations shown by `help <command>`
    """
    
    name: str = ""
    help: str = ""
    usage: str = ""
    tags: list[str] = []
    examples: list[str] = []
    #: Commands that must run on the shell's main thread (they nest
    #: `_execute_line`, touch the terminal, or replace the process).
    #: Such a command may not appear in a multi-stage pipeline.
    main_thread_only: bool = False
    #: Computed in `__init_subclass__`: whether `execute` accepts `stderr=`.
    _accepts_stderr: bool = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # Initialize tags with default if not set
        if not cls.tags:
            cls.tags = ["builtin"]
        
        # Auto-determine command name from filename. `name` is looked up on
        # the class itself (not inherited) so a subclass either declares
        # its own name or gets one from its file.
        if "name" not in cls.__dict__ or not cls.__dict__["name"]:
            file = inspect.getfile(cls)
            cls.name = Path(file).stem
        
        # Validate command name
        if not cls._is_valid_command_name(cls.name):
            raise ValueError(
                f"Invalid command name '{cls.name}': must contain only "
                "alphanumeric characters and underscores, and not start with a digit"
            )
        
        # Third-party plugins written against the old 4-argument `execute`
        # keep working: the executor only passes `stderr=` when accepted.
        try:
            params = inspect.signature(cls.execute).parameters
            cls._accepts_stderr = "stderr" in params
        except (TypeError, ValueError):
            cls._accepts_stderr = False

        # Auto-register command
        from zem.builtins.registry import CommandRegistry
        CommandRegistry.register(cls)

    #: Names that don't fit the identifier rule but are shell conventions.
    #: Only accepted when set explicitly on the class (never auto-derived).
    SPECIAL_NAMES = frozenset({":", ".", "["})

    @classmethod
    def _is_valid_command_name(cls, name: str) -> bool:
        """Validate command name format.

        Args:
            name: Command name to validate

        Returns:
            True if name is valid, False otherwise
        """
        if not name:
            return False
        if name in cls.SPECIAL_NAMES:
            return True
        return bool(re.match(r'^[a-z_][a-z0-9_]*$', name.lower()))

    def _write(self, text: str, stdout: Optional[TextIO] = None) -> None:
        """Write text to stdout.

        Args:
            text: Text to write
            stdout: Output stream (default: sys.stdout)
        """
        (stdout or sys.stdout).write(text)

    def _write_err(self, text: str, stderr: Optional[TextIO] = None) -> None:
        """Write text to stderr.

        Args:
            text: Text to write
            stderr: Error stream (default: sys.stderr)
        """
        (stderr or sys.stderr).write(text)

    def _input(self, stdin: Optional[TextIO] = None) -> str:
        """Read a line from stdin.
        
        Args:
            stdin: Input stream (default: sys.stdin)
            
        Returns:
            Line read from stdin, stripped of trailing newline
        """
        if stdin is None:
            stdin = sys.stdin
        try:
            line = stdin.readline()
            return line.rstrip('\n')
        except (EOFError, OSError):
            return ""
    
    def _read_stdin_all(self, stdin: Optional[TextIO] = None) -> str:
        """Read all content from stdin.
        
        Args:
            stdin: Input stream (default: sys.stdin)
            
        Returns:
            All content from stdin
        """
        if stdin is None or stdin.isatty():
            return ""
        try:
            return stdin.read()
        except (EOFError, OSError):
            return ""

    def _require_args(
        self, 
        args: list[str], 
        min_count: int = 1, 
        error_msg: str = ""
    ) -> None:
        """Validate that minimum required arguments are provided.
        
        Args:
            args: Command arguments
            min_count: Minimum required argument count
            error_msg: Custom error message (default: auto-generated)
            
        Raises:
            ArgumentError: If insufficient arguments provided
        """
        from zem.errors.input_error import ArgumentError
        
        if len(args) < min_count:
            if not error_msg:
                if min_count == 1:
                    error_msg = f"expected at least {min_count} argument"
                else:
                    error_msg = f"expected at least {min_count} arguments"
            raise ArgumentError(self.name, args, error_msg)
    
    def _get_arg(
        self, 
        args: list[str], 
        index: int, 
        default: Optional[str] = None
    ) -> Optional[str]:
        """Safely get argument by index.
        
        Args:
            args: Command arguments
            index: Argument index
            default: Default value if index out of range
            
        Returns:
            Argument value or default
        """
        if 0 <= index < len(args):
            return args[index]
        return default
    
    def _colorize(
        self,
        text: str,
        color: str = "#ffffff"
    ) -> tuple:
        """Create a colored text tuple for FormattedText.
        
        Args:
            text: Text to colorize
            color: Hex color code
            
        Returns:
            Tuple (color, text) for FormattedText
        """
        return (color, text)
    
    def _print_colored(
        self,
        items: list[tuple],
        stdout: Optional[TextIO] = None
    ) -> None:
        """Print colored formatted text, followed by a newline.

        Colors are only emitted when ``stdout`` is a terminal; in pipes,
        redirects and tests prompt_toolkit falls back to plain text, so
        callers never need a separate "plain" branch.

        Args:
            items: List of (style, text) tuples
            stdout: Output stream (default: sys.stdout)
        """
        stream = stdout or sys.stdout
        is_tty = getattr(stream, "isatty", lambda: False)()
        if not is_tty:
            # prompt_toolkit's output layer writes "\r\n" line endings even
            # to plain files; write the text ourselves instead.
            stream.write("".join(text for _style, text in items) + "\n")
            return

        from prompt_toolkit import print_formatted_text
        from prompt_toolkit.formatted_text import FormattedText

        print_formatted_text(FormattedText(items), file=stream)
    
    def _validate_identifier(
        self,
        name: str,
        error_context: str = "variable name"
    ) -> None:
        """Validate that name is a valid Python identifier.
        
        Args:
            name: Name to validate
            error_context: Context for error message
            
        Raises:
            ArgumentError: If name is invalid
        """
        from zem.errors.input_error import ArgumentError
        
        if not name.isidentifier():
            raise ArgumentError(
                self.name,
                name,
                f"{error_context} must be a valid identifier "
                "(letters, digits, underscore, not starting with digit)"
            )

    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin: Optional[TextIO] = None,
        stdout: Optional[TextIO] = None,
        stderr: Optional[TextIO] = None,
    ) -> Optional[int]:
        """Execute the command.

        Args:
            args: Command arguments
            context: Shell execution context (variables, history, commands, etc.)
            stdin: Input stream
            stdout: Output stream
            stderr: Error stream (only passed if your signature declares it)

        Returns:
            Exit code (``int``). Returning ``None`` is treated as ``0`` for
            backward compatibility with older builtins / plugins, but new
            commands should return an explicit ``int``. Conventions:

            * usage error -> raise ``ArgumentError`` (exit 2)
            * runtime failure -> write a message via ``_write_err`` and
              ``return 1``

            Never write ``context.last_exit_code`` from inside ``execute``:
            in pipelines the builtin runs in a worker thread and the
            attribute is shared with sibling stages. Raising a ``CLIError``
            subclass is always safe; the executor maps its ``exit_code``.

        Raises:
            NotImplementedError: Must be implemented in subclasses
        """
        raise NotImplementedError(f"Command '{self.name}' does not implement execute()")
    
    def get_plugin_config(self, context: "ExecutionContext") -> dict:
        """Get configuration for this command/plugin.
        
        Tries to fetch config from context.shell.config.plugins[self.name].
        Returns empty dict if not configured.
        """
        if hasattr(context, '_shell') and context._shell:
            plugins_config = getattr(context._shell.config, 'plugins', {})
            return plugins_config.get(self.name, {})
        return {}

    def get_completer(self) -> Optional["BaseArgCompleter"]:
        """Get the argument completer for this command.
        
        Returns:
            A BaseArgCompleter instance or None if no custom completion is needed.
        """
        return None

    def get_default_config(self) -> dict:
        """Get default configuration for this command/plugin.
        
        Returns:
            Dictionary with default configuration values.
        """
        return {}
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}(name='{self.name}', tags={self.tags})>"
    