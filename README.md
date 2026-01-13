# CLI Shell

A robust, extensible command-line interface shell written in Python.

## Features

- **Built-in Commands**:
  - `add`: Add numbers together.
  - `echo`: Print arguments to stdout.
  - `get`: Retrieve variable values.
  - `set`: Define variables.
  - `unset`: Remove variables.
  - `history`: View command history.
  - `help`: Display help information.
  - `exit`: Exit the shell.

- **Variable Support**:
  - Set variables using `set name value`.
  - Access variables using `get name` or `$name` syntax in other commands (e.g., `echo $name`).
  - Supports `{}` usage for variable names: `${name}`.

- **Persistent History**:
  - Command history is saved to `~/.cli_shell_history` and reloaded on startup.

- **Tab Completion**:
  - Supports tab completion for command names.

- **Robust Error Handling**:
  - Clear, colored error messages for invalid arguments, unknown commands, and parsing errors.

- **Customizible Symbols**:
  - Configurable prompt and variable operators in `src/symbols.py`.

## Installation

This project uses `uv` for dependency management.

1. **Clone the repository**:

    ```bash
    git clone <repository_url>
    cd cli_shell
    ```

2. **Install dependencies**:

    ```bash
    uv sync
    ```

## Usage

Run the shell using:

```bash
uv run main.py
```

Or directly with python if dependencies are installed:

```bash
python3 main.py
```

### Example Session

```bash
>>> set name Anton
>>> echo Hello, $name!
Hello, Anton!
>>> add 10 20.5
30.5
>>> history
  1  set name Anton
  2  echo Hello, $name!
  3  add 10 20.5
  4  history
>>> exit
Closing shell...
```

## Project Structure

```
cli_shell/
├── main.py             # Entry point
├── pyproject.toml      # Project configuration and dependencies
├── README.md           # Documentation
└── src/
    ├── context.py      # Execution context (variables, state)
    ├── parser.py       # Command parser and tokenizer
    ├── shell.py        # Main shell logic (loop, history, completion)
    ├── symbols.py      # Configuration symbols (prompt, operators)
    ├── commands/       # Command implementations
    │   ├── base.py     # Base command class
    │   ├── add.py
    │   ├── echo.py
    │   ├── ...
    └── errors/         # Custom error classes
```

## Development

To add a new command:

1. Create a new file in `src/commands/`.
2. Inherit from `src.commands.base.BaseCommand`.
3. Implement `execute(self, args, context)`.
4. The command will be automatically discovered and loaded.

```python
from src.commands.base import BaseCommand

class MyCommand(BaseCommand):
    name = "mycmd"
    help = "Description of my command"

    def execute(self, args, context):
        print("Hello from my command!")
```
