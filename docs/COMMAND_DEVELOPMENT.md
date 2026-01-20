# Command Development Guide

This guide explains how to develop builtin commands for Axonix shell using the enhanced `BaseCommand` class.

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
from axonix.builtins.base import BaseCommand
from axonix.errors.input_error import ArgumentError
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from axonix.core.context import ExecutionContext


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
        stdout=None
    ):
        """Execute the command."""
        # Validate arguments
        self._require_args(args, min_count=1)
        
        # Use helper methods
        name = args[0]
        self._validate_identifier(name)
        stdin_content = self._read_stdin_all(stdin)
        
        # Command logic here
        result = process(name, stdin_content)
        
        # Output result
        self._write(f"Result: {result}\n", stdout)
```

## Best Practices

1. **Always use `_require_args`** instead of manual `if not args` checks
2. **Use `_validate_identifier`** for variable/alias names
3. **Use `_read_stdin_all`** for reading stdin content safely
4. **Use `_write`** instead of direct `stdout.write()` calls
5. **Provide helpful error messages** via ArgumentError
6. **Document usage** with `help`, `usage`, and `tags` attributes
7. **Test with pipes** to ensure stdin handling works correctly

## Auto-Registration

Commands are automatically registered when they subclass `BaseCommand`. No manual registration needed!

```python
# Just create your command and it's automatically available
class MyNewCommand(BaseCommand):
    help = "My new command"
    
    def execute(self, args, context, stdin=None, stdout=None):
        pass

# No need to manually register - it happens in __init_subclass__!
```
