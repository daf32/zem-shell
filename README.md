# psh

A robust, modular, and highly extensible command-line interface shell written in Python. Designed to mimic real Unix shells with advanced parsing, pipes, and a modern configuration system.

## 🌟 Key Features

- **Advanced Parser**:
  - **Pipelines**: Execute multiple commands in a chain using `|` (e.g., `ls | grep .py`).
  - **Quoting**: Robust support for single (`'`) and double (`"`) quotes.
  - **Escaping**: Use backslashes (`\`) to escape special characters.
  - **Variable Expansion**: Supports `$VAR` and `${VAR}` syntax, including environment variables.

- **Built-in Commands (Builtins)**:
  - Directory Navigation: `cd`, `pwd`.
  - Variable Management: `set`, `get`, `unset`, `export`.
  - Utility: `echo`, `add`, `history`, `help`, `exit`.

- **Modern Configuration**:
  - **Centralized Config**: All operators and shell settings are managed in a root `config.json`.
  - **Pydantic Validation**: Robust type checking and validation for all configuration parameters.
  - **Dynamic Prompt**: Customizable prompt showing truncated path (e.g., `~ dir1/dir2 #`) with configurable depth.

- **Developer Friendly**:
  - **Modular Architecture**: Clean separation between Core, Builtins, and Config.
  - **Persistent History**: Saved to `~/.psh_history`.
  - **Tab Completion**: Intelligent completion for commands.

## 🚀 Installation

This project uses `uv` for dependency management.

1. **Clone the repository**:

    ```bash
    git clone https://github.com/daf32/MyShellCLI.git
    cd psh
    ```

2. **Install dependencies**:

    ```bash
    uv sync
    ```

## 💻 Usage

Run the shell:

```bash
uv run main.py
```

### Example Session

```bash
# Set and use variables
~ psh >>> set name Antigravity
~ psh >>> echo "Hello, $name!"
Hello, Antigravity!

# Pipelines and Builtins
~ psh >>> help | echo
Add numbers together.
Change the shell working directory... (etc)

# Directory Navigation
~ psh >>> cd src/core
~ psh/src/core >>> pwd
/Users/user/projects/psh/src/core
```

## 🛠 Project Structure

```text
psh/
├── main.py             # Entry point with graceful error handling
├── config.json         # JSON configuration (Operators & Settings)
├── pyproject.toml      # Dependency management (pydantic-settings)
└── src/
    ├── core/           # Shell Engine (REPL, Parser, Context)
    ├── builtins/       # Standard command implementations
    │   ├── base.py     # Base class for all builtins
    │   ├── cd.py
    │   └── ...
    ├── config/         # Pydantic Configuration Models
    │   └── settings.py # Central configuration logic
    └── errors/         # Custom exception hierarchy
```

## ⚙️ Configuration (`config.json`)

You can customize almost everything:

```json
{
    "operators": {
        "variable": "$",
        "pipe": "|",
        "escape": "\\"
    },
    "settings": {
        "input": {
            "prompt": ">>>",
            "path_depth": 2,
            "show_full_path": false
        }
    }
}
```

## 👨‍💻 Development

The shell uses an automated discovery system for commands. To add a new builtin:

1. Create a file in `src/builtins/` (e.g., `hello.py`).
2. Inherit from `BaseCommand` and implement `execute`.

```python
from src.builtins.base import BaseCommand

class HelloCommand(BaseCommand):
    name = "hello"
    help = "Say hello"

    def execute(self, args, context, stdin=None, stdout=None):
        if stdout:
            stdout.write("Hello, World!\n")
```

The shell will automatically detect and register your command on the next launch.
