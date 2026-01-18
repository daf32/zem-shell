# Axonix

```text
     █████╗ ██╗  ██╗ ██████╗ ███╗   ██╗██╗██╗  ██╗
    ██╔══██╗╚██╗██╔╝██╔═══██╗████╗  ██║██║╚██╗██╔╝
    ███████║ ╚███╔╝ ██║   ██║██╔██╗ ██║██║ ╚███╔╝ 
    ██╔══██║ ██╔██╗ ██║   ██║██║╚██╗██║██║ ██╔██╗ 
    ██║  ██║██╔╝ ██╗╚██████╔╝██║ ╚████║██║██╔╝ ██╗
    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝
```

Axonix is a modular Python-based shell focused on extensibility and speed.

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
  - **Persistent History**: Saved to `~/.axonix_history`.
  - **Tab Completion**: Intelligent completion for commands.

## 🚀 Installation

This project uses `uv` for dependency management.

1. **Clone the repository**:

    ```bash
    git clone https://github.com/daf32/axonix-shell.git
    cd axonix-shell
    ```

2. **Install dependencies**:

    ```bash
    uv sync
    ```

## 💻 Usage

Run the shell:

```bash
uv run ax
```

### Example Session

```bash
# Set and use variables
~ axonix >>> set name Antigravity
~ axonix >>> echo "Hello, $name!"
Hello, Antigravity!

# Pipelines and Builtins
~ axonix >>> help | echo
Add numbers together.
Change the shell working directory... (etc)

# Directory Navigation
~ axonix/src/axonix/core >>> pwd
/Users/user/projects/axonix-shell/src/axonix/core
```

## 🛠 Project Structure

```text
axonix-shell/
├── config.json         # JSON configuration (Operators & Settings)
├── pyproject.toml      # Dependency management
└── src/
    └── axonix/         # Core package
        ├── main.py     # Entry point
        ├── core/       # Shell Engine (REPL, Parser, Context)
        ├── builtins/   # Standard command implementations
        ├── config/     # Configuration Models
        └── errors/     # Custom exception hierarchy
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

1. Create a file in `src/axonix/builtins/` (e.g., `hello.py`).
2. Inherit from `BaseCommand` and implement `execute`.

```python
from axonix.builtins.base import BaseCommand

class HelloCommand(BaseCommand):
    name = "hello"
    help = "Say hello"

    def execute(self, args, context, stdin=None, stdout=None):
        if stdout:
            stdout.write("Hello, World!\n")
```

The shell will automatically detect and register your command on the next launch.
