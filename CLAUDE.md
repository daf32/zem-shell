# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Zem is a modular Python shell (Python ≥ 3.13) built on `prompt-toolkit` and `pydantic-settings`. The entry point is `zem`, defined in `pyproject.toml` and resolving to `zem.main:main`. Dependency management is done with `uv`.

## Common commands

```bash
# Install / sync dependencies (uv-managed venv at .venv)
uv sync

# Run the shell from source
uv run zem

# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_parser.py::test_quotes_and_variables -v

# Install `ax` globally as a uv tool (from project root)
./scripts/install_zem.sh
./scripts/uninstall_zem.sh

# Build a macOS .app launcher into ./dist
uv run python scripts/build_mac_app.py
```

`ZEM_CONFIG_PATH` overrides the path to `config.json`. The default location is `$XDG_CONFIG_HOME/zem/config.json` (typically `~/.config/zem/config.json`); see `get_config_path()` in `src/zem/config/settings.py`. On first run a legacy `<repo_root>/config.json` is auto-migrated to the new location.

## Architecture

The runtime is a REPL composed of three layers: a parser produces an AST of pipelines/logic units; an executor runs each pipeline by wiring up POSIX pipes between builtins (threads) and external processes (`subprocess.Popen`); a shell loop coordinates input, prompt rendering, history, and rc-file loading.

### Core flow (`src/zem/core/`)

- `shell.py` — `Shell` owns the prompt session, signal handling, terminal state (`termios` is restored on exit; `ECHOCTL` cleared at startup), and the top-level flow `_execute_line` → `_execute_units` → `_execute_pipeline`. Units come from `Parser.iter_units()` lazily, so `$?` and `$(...)` in a later unit see the earlier one's result. `_capture_output` implements `$(...)`. `_run_script_lines`/`_run_script_file` run rc files and `source` (continuation-aware). `Shell(headless=True)` skips prompt_toolkit/termios/signals — every test uses it. Job control: `_wait_job`, `_give_terminal`/`_reclaim_terminal`, `_report_jobs` before each prompt.
- `parser.py` — `Parser` handles quoting, escaping, `$VAR`/`${VAR}`/`$?`, `$(...)` (via a `substitutor` callable), aliases (including parameterized `$1..$N`), `~`/`~user`, globs, redirects (`<`, `>`, `>>`, `2>`, `2>>`, `2>&1`, `&>`, `&>>`), `command CMD` (force_external), and pipeline/logic operators. Expanded text is escaped with `_literal()` before entering the raw token buffer. `scan.py` holds the quote/escape/`$(`-aware scanner shared with the UI, plus `needs_continuation`/`join_lines`; `history_expand.py` does `!!`/`!$`/`!N`/`!prefix`.
- `executor.py` — `_run_builtin` is the single builtin runner; `run_builtin_inline` runs a lone builtin on the main thread, `execute_builtin` wraps it in a daemon thread for pipeline stages (exit code on `thread.exit_code`). Both get `os.dup`'d fds. `execute_external` spawns into a process group with job-control signals reset to default and `env=context.child_env()`.
- `context.py` — `ExecutionContext` (Pydantic) carries `variables` (all shell vars) and `exported` (the subset children inherit); `os.environ` mirrors the exported set and is only written through `set_var`/`unset_var`/`export_var`/`unexport_var`. Also aliases, history, commands, `exit_status`, `_jobs` (`core/jobs.JobTable`), `_dir_stack`, and the `_shell` back-reference. `last_exit_code` mirrors into the shell-local `?` variable.
- `jobs.py` — `Job`/`JobTable` (specs `%N`, `%%`, `%+`, `%-`, `%prefix`, pid), `wait_process` (waitpid with `WUNTRACED`, sets `Popen.returncode`), bash-style notices.

### Builtins and the registry (`src/zem/builtins/`)

- All builtins inherit from `BaseCommand` (`base.py`). `__init_subclass__` auto-derives the command `name` from the filename (snake_case) unless the class sets its own, validates it (`SPECIAL_NAMES` allows `:`, `.`, `[`), and registers the class with `CommandRegistry`. Re-registration is intentionally allowed so external plugins can override builtins.
- `execute()` returns an `int` exit code (`None` → 0 for old plugins); usage errors raise `ArgumentError` (2), runtime failures write via `_write_err` and return 1; error text always goes to stderr. Declare `stderr=` in the signature to receive the stream. `main_thread_only = True` marks commands that nest execution or touch the terminal (`source`, `eval`, `exec`, `fg`, `read`, `exit`); the shell refuses them in multi-stage pipelines.
- `CommandRegistry` (`registry.py`) is a process-wide registry that lazily instantiates command classes. It has no UI side effects; completers are collected by `ZemCompleter`.
- `load_plugins(user_plugins_dir=...)` in `builtins/__init__.py` is invoked once from `Shell.__init__` and imports every module in three locations, in order: `zem.builtins`, `zem.plugins` (bundled plugins, e.g. `weather.py`), and the user plugin dir (`~/.zem/plugins` by default; `None` disables it — tests pass `None`).
- `BaseCommand.get_default_config()` returns plugin defaults; `Shell._sync_plugin_configs()` writes any missing entries into `config.json` under `plugins.<name>` on startup, so plugins ship working config out of the box.
- Helper API on `BaseCommand`: `_require_args`, `_get_arg`, `_validate_identifier`, `_write`, `_write_err`, `_input`, `_read_stdin_all`, `_colorize`, `_print_colored` (plain text when the stream is not a tty), `get_plugin_config`. Shared helpers: `builtins/_cwd.py` (cd/pushd/popd), `_quote.py`, `_test_expr.py`, `_jobspec.py`. See `docs/COMMAND_DEVELOPMENT.md`.

### Configuration (`src/zem/config/settings.py`)

`AppConfig` is a `BaseSettings` model with sections: `operators`, `input`, `history`, `rc`, `colors`, `venv`, `plugins`, plus `active_theme`. Sources, in priority order: init args → `JsonConfigSettingsSource` (path resolved per instance via `get_config_path()`) → env vars. The config file is auto-created from defaults if missing. `validate_unique_operators` rejects any two operators sharing the same symbol — keep this in mind when adding/renaming operators. `format_validation_error` renders pydantic errors as `loc: msg` lines.

All writes to `config.json` go through `config/store.py` (`update_raw`: flock + atomic replace). `config set` validates the candidate document with `AppConfig.model_validate` before writing. Version is read from package metadata (`zem.__version__`); `pyproject.toml` is the only place to bump it.

### UI (`src/zem/ui/`)

- `lexer.py` — `ZemLexer` does live syntax classification (commands, variables, paths, flags, strings, errors). Invalid command names are rendered with the `error` color from the theme.
- `completer.py` + `completers/` — `ZemCompleter` splits the line with `core.scan.word_at` (quote-aware, with offsets), expands a leading alias in full, then picks who completes the command in `_completer_for`: a **user** hint spec → a Python `BaseArgCompleter` from `get_completer()` (`cd` only, now) → a **bundled** hint spec → `EnhancedPathCompleter`, which completes the *current word* (prompt_toolkit's `PathCompleter` would take the whole line). The word under the cursor comes from `Word.text`, not `get_word_before_cursor()`, which cuts at dashes. System commands come from `utils.executables.get_system_commands()`, cached per `PATH` value. `PromptSession` runs completion with `complete_in_thread=True` because specs may shell out.
- `search.py` — `FuzzyHistorySearch` (Ctrl+R) merges file-history with in-memory `context.history`; its style is built from the theme colours.
- `history.py` — `ZemFileHistory` adds `clear()` (used by `history -c`). Ghost-text suggestions come from `AutoSuggestFromHistory` (`input.auto_suggest`).

### Completion hints (`src/zem/hints/`)

Argument completion is declarative: JSON specs in `src/zem/hints/data/` (bundled) and `~/.zem/hints/` (user, replaces bundled by command name; `ZEM_HINTS_PATH` adds directories in between).

- `spec.py` — pydantic models, `extra="forbid"`, `schema_version` gates forward compatibility. `CommandSource.run` rejects `{placeholder}` interpolation (injection vector) but allows Go templates `{{.Name}}`.
- `loader.py` — `HintRegistry`: lazy load, a broken file is recorded in `errors()` and skipped, never raised.
- `resolver.py` — `resolve(spec, words, cursor_index, prefix)`, a pure function: descends subcommands, skips flag values, handles `--flag=value`, `-p8080`, `--`, variadic positionals, and drops `> file` redirections so they don't shift argument indices.
- `sources.py` — resolves a `ValueSource`. The subprocess runner is the delicate part: argv only, `start_new_session=True` (job control uses `tcsetpgrp`; a helper in the foreground group could hang the prompt), `stdin=DEVNULL`, `LC_ALL=C`/`GIT_OPTIONAL_LOCKS=0`, timeout, TTL cache keyed on cwd, optional `guard`, negative caching for missing binaries. Every failure becomes an empty list.
- `providers.py` — `PROVIDERS` registry plus the `@provider` decorator; specs name providers as strings, resolved lazily, which is the seam the plugin API will use.
- `completer.py` — `SpecCompleter(BaseArgCompleter)`: yields static suggestions before dynamic ones (a cancelled round should lose the expensive half), `fallback_to_paths = False` because `spec.fallback` states it explicitly.

- `registry_client.py` — fetches `index.json` and specs over HTTPS for the `hints` builtin: SHA-256 from the index is checked and the spec is validated before it is written to `~/.zem/hints/`. The index cache goes *beside* the spec directory (`cache_path_for`), never inside it — anything `*.json` in there is loaded as a spec.

Bundled specs cover tools almost everyone has; niche ones live in the separate [daf32/zem-hints](https://github.com/daf32/zem-hints) repository (specs in `hints/`, catalogue in `index.json`, validated in its own CI with `zem hints validate`) and are installed with `hints install`. Config section `hints` (`enable`, `dynamic`, `command_timeout_ms`, `cache_ttl_ms`, `user_dir`, `registry_url`). Tests: `tests/hints/`; the suite-wide `_no_hint_subprocess` fixture in `tests/conftest.py` stubs `sources.run_command` so no test depends on a real git/docker, and `tests/hints/conftest.py` overrides it. See `docs/HINT_SPECS.md`.

### Themes (`src/zem/themes/`)

JSON files describing the `ColorScheme`. `ThemeManager` (in `utils/themes.py`) loads/validates them and applies via the `theme` builtin. Every theme JSON must define the `error` key — the lexer relies on it.

### RC file & history

- RC: `~/.zemrc` (path is `config.rc.file`). Auto-created from `src/zem/resources/zemrc.default` on first run if `config.rc.auto_create`. Loaded via `_run_script_file` (comments, blank lines, continuations) through `_execute_line(..., add_to_history=False)`.
- History: `~/.zem_history`, backed by `ZemFileHistory` plus an in-memory list trimmed to `config.history.max_entries`. History expansion (`!!` etc.) applies only to interactive input and can be disabled with `history.expand`.

### Errors

`src/zem/errors/` defines a `CLIError` base with subclasses for parser, input, environment, and execution errors. Each carries an `exit_code` that the shell propagates into `context.last_exit_code`. Builtins should raise these (especially `ArgumentError` from `input_error.py`) rather than printing directly.

## Adding a builtin

Drop a file in `src/zem/builtins/` with a `BaseCommand` subclass — the filename becomes the command name, registration is automatic. For argument completion write a hint spec (`src/zem/hints/data/<name>.json`); `get_completer()` returning a `BaseArgCompleter` is the escape hatch for what a spec cannot express. If it's plugin-like and ships defaults, override `get_default_config()` and read them via `self.get_plugin_config(context)`.

External plugins live in `~/.zem/plugins/` and follow the same pattern. They are loaded last and may override builtins by reusing the same command name.

## Tests

`tests/conftest.py` provides `full_shell` (headless shell with the real builtin registry, user plugins disabled), `make_headless_shell(commands=..., config=...)`, `headless_shell` (no commands), `isolated_config` (history/rc under `tmp_path`), and `run(shell, line) -> (code, out, err)` (fd-level capture, so worker threads and children are included). Autouse fixtures point `ZEM_CONFIG_PATH` at a temp file and snapshot/restore `CommandRegistry` (test-local `BaseCommand` subclasses never leak). Builtin tests live in `tests/builtins/`; parser cases in `tests/test_parser.py` use `_args(line)` / `_cmd(line)` helpers. Job-control tests spawn real `/bin/sleep` processes; keep them killed in fixtures.

Run with `uv run pytest` (or `.venv/bin/python -m pytest` if `uv run` cannot spawn in your sandbox). CI runs ruff (`E,F,I,B`), mypy (non-blocking baseline) and pytest on Linux and macOS.
