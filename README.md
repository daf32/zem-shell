# Zem

```text
    ███████╗███████╗███╗   ███╗
    ╚══███╔╝██╔════╝████╗ ████║
      ███╔╝ █████╗  ██╔████╔██║
     ███╔╝  ██╔══╝  ██║╚██╔╝██║
    ███████╗███████╗██║ ╚═╝ ██║
    ╚══════╝╚══════╝╚═╝     ╚═╝
```

Zem is a modular Python-based shell focused on extensibility and speed.

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

- **UI**: syntax highlighting, fish-style ghost-text suggestions from history,
  Ctrl-R fuzzy history search, themes (`theme list`), git/venv/exit-code/duration
  in the prompt.

- **Completion that knows your tools**: `git checkout <TAB>` lists your branches,
  `git push <TAB>` your remotes, `docker exec <TAB>` your running containers,
  `npm run <TAB>` the scripts in `package.json`, `make <TAB>` your targets. Ships
  with specs for git, docker, npm, pip, uv, kubectl, brew, gh, ssh, make and go —
  and a spec is just JSON, so adding your own tool means dropping a file in
  `~/.zem/hints/`. More tools (`kubectl`, `brew`, `gh`, `go`, …) install on
  demand from the [spec registry](https://github.com/daf32/zem-hints) with
  `hints install kubectl`. See [docs/HINT_SPECS.md](docs/HINT_SPECS.md).

- **Configuration**: one validated JSON file (`config set` refuses values the shell
  could not start with), `~/.zemrc`, plugins in `~/.zem/plugins/`.

## Non-interactive use

```bash
zem -c "git status | grep modified"   # run one command, exit with its status
zem build.zem                          # run a script
echo "echo hi" | zem                   # or read it from stdin
```

`~/.zemrc` is not read in these modes (as in bash, zsh and fish), so a script
behaves the same on a machine whose owner has never customised anything. Pass
`--rc` if you want your aliases.

## 🚀 Installation

### From PyPI

```bash
uv tool install zem      # recommended: uv fetches a suitable Python itself
```

or, with a Python 3.10+ already on your PATH:

```bash
pip install zem
```

### From source

This project uses `uv` for dependency management.

1. **Clone the repository**:

    ```bash
    git clone https://github.com/daf32/zem-shell.git
    cd zem-shell
    ```

2. **Install dependencies**:

    ```bash
    uv sync
    ```

3. **Optional — install `zem` globally as a uv tool**:

    ```bash
    ./scripts/install_zem.sh
    ```

## 💻 Usage

Run the shell from the checkout (or just `zem` after the global install):

```bash
uv run zem
```

`zem --version` prints the installed version.

### Example Session

```bash
# Variables: shell-local vs exported
~ zem # set name Antigravity
~ zem # echo "Hello, $name!"
Hello, Antigravity!
~ zem # export EDITOR=vim

# Substitution, tests, redirections
~ zem # echo "today is $(date +%A)"
~ zem # [ -d .git ] && echo "in a repo" || echo "not a repo"
~ zem # make 2> build.log

# Pipelines with builtins
~ zem # help | grep -i theme

# Jobs
~ zem # sleep 30 &
[1] 4242
~ zem # jobs
[1]+ Running                 sleep 30
~ zem # kill %1
```

## 🛠 Project Structure

```text
zem-shell/
├── pyproject.toml      # Dependency management
└── src/
    └── zem/            # Core package
        ├── main.py     # Entry point
        ├── core/       # Shell engine: REPL, parser, executor, jobs, context
        ├── builtins/   # Standard command implementations
        ├── plugins/    # Bundled plugins (e.g. weather)
        ├── ui/         # Lexer, completers, history search
        ├── themes/     # Colour themes (JSON)
        ├── config/     # Configuration models and the config-file store
        └── errors/     # Custom exception hierarchy
```

The user-level configuration lives at `~/.config/zem/config.json`
(or `$XDG_CONFIG_HOME/zem/config.json`). Override with `ZEM_CONFIG_PATH`.

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

1. Create a file in `src/zem/builtins/` (e.g., `hello.py`).
2. Inherit from `BaseCommand` and implement `execute`.

```python
from zem.builtins.base import BaseCommand

class HelloCommand(BaseCommand):
    name = "hello"
    help = "Say hello"

    def execute(self, args, context, stdin=None, stdout=None, stderr=None) -> int:
        self._write("Hello, World!\n", stdout)
        return 0
```

The shell will automatically detect and register your command on the next launch.
See `docs/COMMAND_DEVELOPMENT.md` for the full API (exit codes, streams, variables,
completion, plugin config). User plugins go in `~/.zem/plugins/`, completion specs in `~/.zem/hints/`.

Run the tests with `uv run pytest`; lint with `uv run ruff check .`.

### Releasing

Releases are cut automatically from the **branch name** of the merged PR:

| branch prefix | bump | example |
|---|---|---|
| `patch/...` | patch | 1.2.3 → 1.2.4 |
| `minor/...` | minor | 1.2.3 → 1.3.0 |
| `major/...` | major | 1.2.3 → 2.0.0 |
| anything else | none | no release |

On merge, `version-bump.yml` updates `pyproject.toml`, `uv.lock` and the
`Unreleased` section of `CHANGELOG.md`, commits `chore(release): vX.Y.Z` to
`main`, tags it and runs `release.yml`, which publishes to PyPI and creates the
GitHub Release. Put user-visible changes under **Unreleased** in the CHANGELOG
while working on the PR.
