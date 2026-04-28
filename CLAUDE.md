# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Axonix is a modular Python shell (Python ≥ 3.13) built on `prompt-toolkit` and `pydantic-settings`. The entry point is `ax`, defined in `pyproject.toml` and resolving to `axonix.main:main`. Dependency management is done with `uv`.

## Common commands

```bash
# Install / sync dependencies (uv-managed venv at .venv)
uv sync

# Run the shell from source
uv run ax

# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_parser.py::test_quotes_and_variables -v

# Install `ax` globally as a uv tool (from project root)
./scripts/install_axonix.sh
./scripts/uninstall_axonix.sh

# Build a macOS .app launcher into ./dist
uv run python scripts/build_mac_app.py
```

`AXONIX_CONFIG_PATH` overrides the path to `config.json`. The default location is `$XDG_CONFIG_HOME/axonix/config.json` (typically `~/.config/axonix/config.json`); see `get_config_path()` in `src/axonix/config/settings.py`. On first run a legacy `<repo_root>/config.json` is auto-migrated to the new location.

## Architecture

The runtime is a REPL composed of three layers: a parser produces an AST of pipelines/logic units; an executor runs each pipeline by wiring up POSIX pipes between builtins (threads) and external processes (`subprocess.Popen`); a shell loop coordinates input, prompt rendering, history, and rc-file loading.

### Core flow (`src/axonix/core/`)

- `shell.py` — `Shell` owns the prompt session, signal handling, terminal state (`termios` is restored on exit; `ECHOCTL` cleared at startup), and the top-level `_execute_line` → `_execute_pipeline` flow. Logic operators `&&`, `||`, `;` are evaluated between pipeline units. The shell takes terminal control via `os.tcsetpgrp` only when at least one external process is in the pipeline.
- `parser.py` — `Parser` handles quoting, escaping, variable expansion (`$VAR`, `${VAR}`), aliases (including parameterized `$1..$N`), glob expansion, redirects (`<`, `>`, `>>`), and pipeline/logic operators. Operator characters come from `config.operators` and are validated for uniqueness in `AppConfig`.
- `executor.py` — `CommandExecutor.execute_builtin` runs each builtin in a daemon thread with managed file descriptors (`managed_fd` ctx manager). `execute_external` spawns subprocesses into a process group (first child becomes pgid leader). It also pulls a fresh `PATH` by sourcing the user's `~/.zshrc`/`~/.bashrc` to keep newly-installed binaries discoverable.
- `context.py` — `ExecutionContext` (a Pydantic model) carries variables, aliases, history, registered commands, the active venv, and a `_shell` back-reference used by plugins to read `config.plugins[name]`. `last_exit_code` is a property that mirrors into the `?` variable.

### Builtins and the registry (`src/axonix/builtins/`)

- All builtins inherit from `BaseCommand` (`base.py`). `__init_subclass__` auto-derives the command `name` from the filename (snake_case), validates it, and registers the class with `CommandRegistry`. Re-registration is intentionally allowed so external plugins can override builtins.
- `CommandRegistry` (`registry.py`) is a singleton that lazily instantiates command classes and, on `get_all_commands`, also pulls each instance's `get_completer()` and registers it with `CompleterRegistry`.
- `load_plugins()` in `builtins/__init__.py` is invoked once from `Shell.__init__` and imports every module in three locations, in order: `axonix.builtins`, `axonix.plugins` (bundled plugins, e.g. `weather.py`), and `~/.axonix/plugins` (user plugins added to `sys.path`).
- `BaseCommand.get_default_config()` returns plugin defaults; `Shell._sync_plugin_configs()` writes any missing entries into `config.json` under `plugins.<name>` on startup, so plugins ship working config out of the box.
- Helper API on `BaseCommand`: `_require_args`, `_get_arg`, `_validate_identifier`, `_write`, `_input`, `_read_stdin_all`, `_colorize`, `_print_colored`, `get_plugin_config`. See `docs/COMMAND_DEVELOPMENT.md`.

### Configuration (`src/axonix/config/settings.py`)

`AppConfig` is a `BaseSettings` model with sections: `operators`, `input`, `history`, `rc`, `colors`, `venv`, `plugins`, plus `active_theme`. Sources, in priority order: init args → `JsonConfigSettingsSource` (the `config.json`) → env vars. The config file is auto-created from defaults if missing. `validate_unique_operators` rejects any two operators sharing the same symbol — keep this in mind when adding/renaming operators.

### UI (`src/axonix/ui/`)

- `lexer.py` — `AxonixLexer` does live syntax classification (commands, variables, paths, flags, strings, errors). Invalid command names are rendered with the `error` color from the theme.
- `completer.py` + `completers/` — `AxonixCompleter` resolves completions in this order: command-name position → registered `CompleterRegistry` entry for the command (or the alias's resolved target) → `EnhancedPathCompleter` fallback. Default completers registered: `git`, `cd`, `theme`, `pip`, `pip3`, `docker`, `npm`, `npx`, `yarn`, `pnpm`. New commands provide their own via `BaseCommand.get_completer()`.
- `search.py` — `FuzzyHistorySearch` (Ctrl+R) merges file-history with in-memory `context.history`.

### Themes (`src/axonix/themes/`)

JSON files describing the `ColorScheme`. `ThemeManager` (in `utils/themes.py`) loads/validates them and applies via the `theme` builtin. Every theme JSON must define the `error` key — the lexer relies on it.

### RC file & history

- RC: `~/.axonixrc` (path is `config.rc.file`). Auto-created from `src/axonix/resources/axonixrc.default` on first run if `config.rc.auto_create`. Loaded via `_load_rc_file` line-by-line through `_execute_line(..., add_to_history=False)`.
- History: `~/.axonix_history`, backed by `prompt_toolkit.history.FileHistory` plus an in-memory list trimmed to `config.history.max_entries`.

### Errors

`src/axonix/errors/` defines a `CLIError` base with subclasses for parser, input, environment, and execution errors. Each carries an `exit_code` that the shell propagates into `context.last_exit_code`. Builtins should raise these (especially `ArgumentError` from `input_error.py`) rather than printing directly.

## Adding a builtin

Drop a file in `src/axonix/builtins/` with a `BaseCommand` subclass — the filename becomes the command name, registration is automatic. If the command needs argument completion, override `get_completer()` to return a `BaseArgCompleter`. If it's plugin-like and ships defaults, override `get_default_config()` and read them via `self.get_plugin_config(context)`.

External plugins live in `~/.axonix/plugins/` and follow the same pattern. They are loaded last and may override builtins by reusing the same command name.

## Tests

`tests/` uses `pytest` directly (no conftest fixtures). Tests construct `AppConfig()` and `Parser(...)` against in-memory dicts — no shell instance needed. When adding parser features, prefer extending `tests/test_parser.py` with focused cases.
