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
- Builtin output was silently lost on `>` redirects and builtin-to-builtin
  pipes because the main thread and the worker thread closed the same file
  descriptor.
- First run with a missing config file crashed with `JSONDecodeError`.

### Removed
- The `add` test builtin is no longer shipped to users.
