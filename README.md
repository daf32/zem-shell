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

- **Interactive-shell syntax** (fish-like scope: no `if`/`for`/functions — run scripts with bash):
  - Pipelines `|`, logic `&&` `||` `;`, background `&`.
  - Quoting, backslash escapes, `$VAR`, `${VAR}`, `$?`, `$(...)` command substitution.
  - Redirections `<` `>` `>>` `2>` `2>>` `2>&1` `&>`; `~` and `~user` expansion; globs.
  - Line continuation (trailing `\`, open quote, trailing operator) and
    history expansion `!!` `!$` `!N` `!prefix`.
  - Aliases with parameters (`alias gc='git commit -m $1'`).

- **Job control**: Ctrl-Z, `jobs`, `fg`, `bg`, `wait`, `kill %1`, `disown`.

- **Builtins**: `cd` `pwd` `pushd` `popd` `dirs` · `set` `get` `unset` `export`
  `alias` `unalias` · `echo` `printf` `read` `test`/`[` `true` `false` `:` ·
  `type` `command` `source`/`.` `eval` `exec` · `history` `help` `config`
  `theme` `venv` `logo` `exit`. Every builtin returns a proper exit code and
  reports errors on stderr, so `help | grep cd` and `theme set x || echo no` behave.

- **Variables done right**: `set NAME v` is shell-local, `export NAME` promotes it;
  children only see exported variables.

- **UI**: syntax highlighting, tab completion (commands, paths, `git`/`pip`/`docker`/`npm`
  arguments), fish-style ghost-text suggestions from history, Ctrl-R fuzzy history
  search, themes (`theme list`), git/venv/exit-code/duration in the prompt.

- **Configuration**: one validated JSON file (`config set` refuses values the shell
  could not start with), `~/.axonixrc`, plugins in `~/.axonix/plugins/`.

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

3. **Optional — install `ax` globally as a uv tool**:

    ```bash
    ./scripts/install_axonix.sh
    ```

## 💻 Usage

Run the shell from the checkout (or just `ax` after the global install):

```bash
uv run ax
```

`ax --version` prints the installed version.

### Example Session

```bash
# Variables: shell-local vs exported
~ axonix # set name Antigravity
~ axonix # echo "Hello, $name!"
Hello, Antigravity!
~ axonix # export EDITOR=vim

# Substitution, tests, redirections
~ axonix # echo "today is $(date +%A)"
~ axonix # [ -d .git ] && echo "in a repo" || echo "not a repo"
~ axonix # make 2> build.log

# Pipelines with builtins
~ axonix # help | grep -i theme

# Jobs
~ axonix # sleep 30 &
[1] 4242
~ axonix # jobs
[1]+ Running                 sleep 30
~ axonix # kill %1
```

## 🛠 Project Structure

```text
axonix-shell/
├── pyproject.toml      # Dependency management
└── src/
    └── axonix/         # Core package
        ├── main.py     # Entry point
        ├── core/       # Shell engine: REPL, parser, executor, jobs, context
        ├── builtins/   # Standard command implementations
        ├── plugins/    # Bundled plugins (e.g. weather)
        ├── ui/         # Lexer, completers, history search
        ├── themes/     # Colour themes (JSON)
        ├── config/     # Configuration models and the config-file store
        └── errors/     # Custom exception hierarchy
```

The user-level configuration lives at `~/.config/axonix/config.json`
(or `$XDG_CONFIG_HOME/axonix/config.json`). Override with `AXONIX_CONFIG_PATH`.

## ⚙️ Configuration (`config.json`)

Edit the file directly, or from inside the shell with `config set KEY VALUE`
(values are validated against the schema before they are written; `config list`
shows every key):

```json
{
    "operators": {
        "variable": "$",
        "pipe": "|",
        "escape": "\\"
    },
    "input": {
        "prompt": ">>>",
        "path_depth": 2,
        "show_full_path": false,
        "auto_suggest": true
    },
    "history": {
        "max_entries": 1000,
        "expand": true
    },
    "active_theme": "dracula"
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

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        self._write("Hello, World!\n", stdout)
        return 0
```

The shell will automatically detect and register your command on the next launch.
See `docs/COMMAND_DEVELOPMENT.md` for the full API (exit codes, streams, variables,
completion, plugin config). User plugins go in `~/.axonix/plugins/`.

Run the tests with `uv run pytest`; lint with `uv run ruff check .`.
