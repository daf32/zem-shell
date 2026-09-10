# Changelog

All notable changes to Axonix are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- **Variable model.** `set NAME` now creates a shell-local variable; only
  exported variables (inherited from the environment, or promoted with
  `export`) reach child processes. Previously every `set` variable and
  even `?` leaked into children, and `unset` of an inherited variable was
  silently undone on the next line. Reassigning an inherited name such as
  `PATH` keeps it exported, so existing `~/.axonixrc` files work unchanged.
- A single builtin on a line runs on the main thread; pipeline stages
  still run in worker threads. Commands marked `main_thread_only` are
  rejected in pipelines with a clear error.
- `exit [n]` sets the shell's exit status (propagated to the parent
  process) and no longer prints "Closing shell...".
- Error messages from builtins go to stderr instead of the stdout pipe.
- `help`, `theme`, `logo`, `history`, `weather` print plain text when
  piped or redirected instead of writing colours to the terminal.

- `set` lists variables when called bare, gains `-x` (export) and `-e`
  (erase). `export` accepts bare `NAME` (promote), `-n NAME` (unexport)
  and lists only exported variables in re-sourceable form. `unset` takes
  several names and no longer fails on unknown ones. `get` distinguishes
  an empty value from an unset variable. `alias` output is re-sourceable
  and no longer mangles values containing quotes; `unalias -a` added.
  Missing aliases/variables report on stderr with exit code 1.

- `cd` tracks the logical path (symlinks kept in `$PWD`), exports
  `PWD`/`OLDPWD`, supports `~user`, errors on `cd -` only when `OLDPWD` is
  unset, rejects extra arguments. `pwd` gains `-L`/`-P`. `echo` gains
  `-n`, `-e`, `-E`. `history` parses arguments strictly, `-c` now also
  clears the history file, `-d N` deletes one entry. `theme` uses the live
  config, returns 1 on every failure and reports on stderr. `venv activate`
  accepts a path; the silent `venv on`/`off` no-ops are gone. `help nope`
  exits 1.

### Added
- `BaseCommand.execute` may declare `stderr=`; `_write_err()` helper.
- `ExecutionContext.set_var/unset_var/export_var/unexport_var/child_env`.
- `ax --version` / `ax -V` prints the installed version.
- `axonix.__version__`, read from package metadata (single source of truth is
  `pyproject.toml`).
- GitHub Actions CI: ruff, mypy (non-blocking baseline), pytest on Linux and
  macOS.
- `Shell(user_plugins_dir=...)` / `load_plugins(user_plugins_dir=...)` so the
  external plugin directory can be redirected or disabled (used by tests).
- `BaseCommand.examples` is now a declared attribute shown by `help <command>`.
- Test fixtures: `full_shell` (real builtin registry, headless) and `run()`.

### Fixed
- `AppConfig` read the config path once at class definition, so changing
  `AXONIX_CONFIG_PATH` after import (or in tests) was ignored.
- Coloured builtins wrote CRLF line endings when redirected to a file.
- `echo a\'b` printed `ab`: the tokenizer dropped the backslash but kept
  the quote, which the quote-removal pass then treated as an opener.
- Builtin output was silently lost on `>` redirects and builtin-to-builtin
  pipes because the main thread and the worker thread closed the same file
  descriptor.
- First run with a missing config file crashed with `JSONDecodeError`.

### Removed
- The `add` test builtin is no longer shipped to users.
