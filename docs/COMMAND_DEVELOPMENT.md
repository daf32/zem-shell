# Command Development Guide

This guide explains how to develop builtin commands for Zem shell using the enhanced `BaseCommand` class.

## BaseCommand Helper Methods

The `BaseCommand` class provides several utility methods to reduce boilerplate code and ensure consistency across commands.

### 1. Argument Validation

#### `_require_args(args, min_count, error_msg)`
Validate that minimum required arguments are provided.

```python
def execute(self, args, context, stdin=None, stdout=None):
    # Requires exactly 1 argument
    self._require_args(args, min_count=1)
    
    # Requires at least 2 arguments with custom message
    self._require_args(args, min_count=2, error_msg="expected NAME and VALUE")
```

#### `_get_arg(args, index, default)`
Safely get argument by index without IndexError.

```python
def execute(self, args, context, stdin=None, stdout=None):
    name = self._get_arg(args, 0)  # Returns None if not available
    value = self._get_arg(args, 1, default="")  # Returns "" if not available
```

#### `_validate_identifier(name, error_context)`
Ensure a name is a valid Python identifier (for variable/alias names).

```python
def execute(self, args, context, stdin=None, stdout=None):
    name = args[0]
    self._validate_identifier(name)  # Raises ArgumentError if invalid
    self._validate_identifier(name, error_context="custom entity name")
```

### 2. Input/Output

#### `_write(text, stdout)`
Safely write to stdout.

```python
def execute(self, args, context, stdin=None, stdout=None):
    self._write("Hello, World!\n", stdout)
    # Automatically handles None stdout gracefully
```

#### `_input(stdin)`
Read a single line from stdin.

```python
def execute(self, args, context, stdin=None, stdout=None):
    line = self._input(stdin)  # Returns empty string on error
```

#### `_read_stdin_all(stdin)`
Read all content from stdin (if not a TTY).

```python
def execute(self, args, context, stdin=None, stdout=None):
    content = self._read_stdin_all(stdin)
    for token in content.split():
        process(token)
```

### 3. Colored Output

#### `_colorize(text, color)`
Create a colored text tuple.

```python
def execute(self, args, context, stdin=None, stdout=None):
    colored = self._colorize("Success!", "#50fa7b")  # Returns ("#50fa7b", "Success!")
```

#### `_print_colored(items, stdout)`
Print colored formatted text using prompt_toolkit.

```python
def execute(self, args, context, stdin=None, stdout=None):
    items = [
        self._colorize("✓ ", "#50fa7b"),
        ("", "Operation completed!")
    ]
    self._print_colored(items, stdout)
```

## Before and After Examples

### Before (Without Helpers)
```python
class OldCommand(BaseCommand):
    def execute(self, args, context, stdin=None, stdout=None):
        if not args:
            raise ArgumentError(self.name, "", "expected NAME")
        
        name = args[0]
        if not name.isidentifier():
            raise ArgumentError(
                self.name,
                name,
                "variable name must be a valid identifier..."
            )
        
        if stdin and not stdin.isatty():
            try:
                content = stdin.read()
                # process content
            except (EOFError, OSError):
                pass
        
        if stdout:
            stdout.write(f"Result: {result}\n")
```

### After (With BaseCommand Helpers)
```python
class NewCommand(BaseCommand):
    def execute(self, args, context, stdin=None, stdout=None):
        self._require_args(args, min_count=1, error_msg="expected NAME")
        
        name = args[0]
        self._validate_identifier(name)
        
        content = self._read_stdin_all(stdin)
        # process content
        
        self._write(f"Result: {result}\n", stdout)
```

Much cleaner! 🎉

## Creating a New Command

Here's a template for a new builtin command:

```python
from zem.builtins.base import BaseCommand
from zem.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zem.core.context import ExecutionContext


class MyCommand(BaseCommand):
    """Brief description."""
    
    name = "mycommand"  # Optional: auto-detected from filename
    help = "Detailed help text"
    usage = "mycommand [options] [arguments]"
    tags = ["builtin", "category"]
    
    def execute(
        self,
        args: list[str],
        context: "ExecutionContext",
        stdin=None,
        stdout=None,
        stderr=None,   # optional; only passed if you declare it
    ) -> int:
        """Execute the command and return an exit code."""
        # Validate arguments (raises ArgumentError -> exit code 2)
        self._require_args(args, min_count=1)

        name = args[0]
        self._validate_identifier(name)
        stdin_content = self._read_stdin_all(stdin)

        result = process(name, stdin_content)
        if result is None:
            # Runtime failure: message on stderr, non-zero exit code
            self._write_err(f"{self.name}: nothing to do for {name}\n", stderr)
            return 1

        self._write(f"Result: {result}\n", stdout)
        return 0
```

## Exit Codes and Streams

* Return an `int`. `None` is accepted for backwards compatibility and
  means `0`, but new commands should be explicit.
* Usage errors: raise `ArgumentError` (exit code 2). Any `CLIError`
  subclass is mapped to its `exit_code` and its message is printed to
  stderr by the executor, never into the stdout pipe.
* Runtime failures: write a message with `_write_err(...)` and `return 1`.
* Never assign `context.last_exit_code` inside `execute`. In pipelines the
  builtin runs in a worker thread and that attribute is shared.
* Colored output goes through `_print_colored(items, stdout)`. It degrades
  to plain text automatically when stdout is a pipe, a file or a test
  buffer, so `help | grep cd` and `help > out.txt` just work.

## Variables and the Environment

`context.variables` holds every shell variable; `context.exported` is the
subset children inherit. Use the API instead of touching `os.environ`:

```python
context.set_var("FOO", "1")                  # shell-local (new name)
context.set_var("PATH", new_path)            # stays exported (inherited name)
context.set_var("BAR", "x", export=True)     # force export
context.export_var("FOO")                    # promote an existing variable
context.unexport_var("FOO")                  # keep the value, hide from children
context.unset_var("FOO")                     # remove everywhere
context.child_env()                          # dict passed to subprocesses
```

The `?` pseudo-variable (last exit code) is shell-local and never exported.

## Main-Thread-Only Commands

A single builtin on a line runs inline on the shell's main thread. Stages
of a multi-command pipeline run in worker threads. If your command must
never run in a worker (it nests shell execution, touches the terminal, or
replaces the process — think `source`, `exec`, `fg`), set
`main_thread_only = True`; the shell then refuses to put it in a pipeline
with a clear error instead of misbehaving.

## Best Practices

1. **Return an `int` exit code** from `execute`
2. **Always use `_require_args`** instead of manual `if not args` checks
3. **Use `_validate_identifier`** for variable/alias names
4. **Use `_read_stdin_all`** for reading stdin content safely
5. **Use `_write` / `_write_err`** instead of direct stream writes
6. **Provide helpful error messages** via ArgumentError
7. **Document usage** with `help`, `usage`, `tags` and `examples` attributes
8. **Test with pipes and redirects** to ensure stdin/stdout handling works

## Completion and Plugin Config

* Override `get_completer()` to return a `BaseArgCompleter` for argument
  completion (see `src/zem/ui/completers/base.py`).
* Override `get_default_config()` to ship defaults; the shell writes them
  into `config.json` under `plugins.<name>` on first start. Read them back
  with `self.get_plugin_config(context)`.

## External Plugins

Drop a `.py` file into `~/.zem/plugins/`. It is imported after the
bundled commands and may reuse a builtin's name to override it.

## Auto-Registration

Commands are automatically registered when they subclass `BaseCommand`. No manual registration needed!

```python
# Just create your command and it's automatically available
class MyNewCommand(BaseCommand):
    help = "My new command"
    
    def execute(self, args, context, stdin=None, stdout=None):
        return 0

# No need to manually register - it happens in __init_subclass__!
```
