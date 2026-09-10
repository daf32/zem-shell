# BaseCommand Helper Methods Reference

## 📚 Quick Reference

| Method | Purpose | Example |
|--------|---------|---------|
| `_write(text, stdout)` | Write to stdout | `self._write("Result\n", stdout)` |
| `_write_err(text, stderr)` | Write to stderr | `self._write_err("oops\n", stderr)` |
| `_input(stdin)` | Read single line from stdin | `line = self._input(stdin)` |
| `_read_stdin_all(stdin)` | Read all stdin content | `content = self._read_stdin_all(stdin)` |
| `_require_args(args, min_count)` | Validate argument count | `self._require_args(args, 2)` |
| `_get_arg(args, index, default)` | Safe argument access | `name = self._get_arg(args, 0, "default")` |
| `_validate_identifier(name)` | Check valid Python identifier | `self._validate_identifier(var_name)` |
| `_colorize(text, color)` | Create colored tuple | `self._colorize("✓", "#50fa7b")` |
| `_print_colored(items, stdout)` | Print colored output (plain in pipes) | `self._print_colored([(color, text)], stdout)` |

`execute` should return an `int` exit code (`0` on success). See
`COMMAND_DEVELOPMENT.md` → "Exit Codes and Streams".

## 🎯 Common Patterns

### Pattern 1: Simple Command with Arguments
```python
class EchoCommand(BaseCommand):
    help = "Print arguments"
    
    def execute(self, args, context, stdin=None, stdout=None):
        self._write(" ".join(args) + "\n", stdout)
```

### Pattern 2: Variable Management
```python
class SetCommand(BaseCommand):
    help = "Set variable"
    
    def execute(self, args, context, stdin=None, stdout=None):
        self._require_args(args, min_count=1, error_msg="expected NAME and VALUE")
        name = args[0]
        self._validate_identifier(name)
        value = " ".join(args[1:])
        context.variables[name] = value
```

### Pattern 3: Reading from Stdin
```python
class AddCommand(BaseCommand):
    help = "Add numbers"
    
    def execute(self, args, context, stdin=None, stdout=None):
        numbers = [float(x) for x in args]
        content = self._read_stdin_all(stdin)
        for token in content.split():
            numbers.append(float(token))
        self._write(str(sum(numbers)) + "\n", stdout)
```

### Pattern 4: Colored Output
```python
class StatusCommand(BaseCommand):
    help = "Show status"
    
    def execute(self, args, context, stdin=None, stdout=None):
        items = [
            self._colorize("✓ ", "#50fa7b"),
            ("", "Ready")
        ]
        self._print_colored(items, stdout)
```

### Pattern 5: Optional Arguments
```python
class GetCommand(BaseCommand):
    help = "Get variable value"
    
    def execute(self, args, context, stdin=None, stdout=None):
        self._require_args(args, min_count=1)
        name = self._get_arg(args, 0)
        default_val = self._get_arg(args, 1, "not set")
        value = context.variables.get(name, default_val)
        self._write(f"{name}={value}\n", stdout)
```

## 🔄 Migration Examples

### Before → After

#### Example 1: Argument Validation
**Before:**
```python
if not args:
    raise ArgumentError(self.name, "", "expected NAME")
name = args[0]
```

**After:**
```python
self._require_args(args, min_count=1, error_msg="expected NAME")
name = self._get_arg(args, 0)
```

#### Example 2: Identifier Validation
**Before:**
```python
if not name.isidentifier():
    raise ArgumentError(
        self.name,
        name,
        "variable name must be a valid identifier..."
    )
```

**After:**
```python
self._validate_identifier(name)
```

#### Example 3: Stdin Reading
**Before:**
```python
if stdin and not stdin.isatty():
    try:
        content = stdin.read()
    except (EOFError, OSError):
        content = ""
```

**After:**
```python
content = self._read_stdin_all(stdin)
```

#### Example 4: Output
**Before:**
```python
if stdout:
    stdout.write(text + "\n")
```

**After:**
```python
self._write(text + "\n", stdout)
```

## 📊 Code Reduction

| Command | Before (lines) | After (lines) | Reduction |
|---------|---|---|---|
| set.py | 14 | 9 | -36% |
| get.py | 11 | 7 | -36% |
| **Total** | **50** | **36** | **-28%** |

These helper methods significantly reduce boilerplate and improve consistency! 🚀
