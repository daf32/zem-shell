# Changelog

All notable changes to Axonix are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
