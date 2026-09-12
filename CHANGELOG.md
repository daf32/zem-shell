# Changelog

All notable changes to Zem are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.10.0] - 2026-09-12
### Added
- **Declarative completion hints.** Argument completion is now driven by JSON
  specs describing a command's subcommands, flags and where their values come
  from, executed by one engine. Dynamic values are real: `git checkout` lists
  your branches, `git push` your remotes, `git add` your changed files,
  `docker exec` your running containers, `npm run` the scripts in
  `package.json`, `make` your targets, `ssh` the hosts in `~/.ssh/config`,
  `theme set` your themes, `config get` the live config keys.
- Specs ship for git, pip, docker, npm, npx, uv, kubectl, brew, gh, ssh, make,
  go, plus zem's own `theme`, `config` and `weather`. Drop a JSON file in
  `~/.zem/hints/` to add your own tool or replace a bundled spec — see
  `docs/HINT_SPECS.md`. New config section `hints`, including
  `hints.dynamic = false` to stop specs shelling out entirely.
- Completion now runs on a worker thread, so a spec that shells out cannot
  stall the prompt.
- **`hints` command and a spec registry.** The wheel ships specs only for
  tools almost everyone has; the rest are fetched on demand with
  `hints search` / `hints install` / `hints update` / `hints remove`, which
  verify each download's checksum and validate it before writing to
  `~/.zem/hints/`. `hints list`, `hints show <command>`, `hints validate` and
  `hints providers` cover inspection and writing your own. The default
  registry is [daf32/zem-hints](https://github.com/daf32/zem-hints); point
  `hints.registry_url` at your own if you like.

### Fixed
- Flags with a typed prefix complete again. `pip install --upg<TAB>` produced
  nothing at all: the word under the cursor was cut at the dash, so no flag
  matched, and the path fallback was suppressed because the word began with
  `-`. Every flag branch of the git/pip/docker/npm completers was dead code.
- An alias is expanded in full during completion. With
  `alias gs='git status'`, `gs <TAB>` offered git's subcommands as though
  `status` had not been typed.
- Completion splits the line the way the shell does: quoted arguments count as
  one word, and a `> out.txt` redirection no longer counts as an argument.

### Changed
- `BaseArgCompleter` and `get_completer()` are unchanged and still take
  precedence over a bundled spec, so plugins that implement them keep working.
  Two details they observe did change: `word_before` now keeps leading dashes,
  and `parts` is quote-aware with the alias expanded.

## [0.9.12] - 2026-09-10
### Removed
- Automatic migration of files from the pre-rename layout
  (`~/.config/axonix`, `~/.axonixrc`, `~/.axonix_history`, `~/.axonix/`).

## [0.9.11] - 2026-09-10
### Changed
- Python 3.10+ is supported (was 3.13+). `pip install zem` now works on
  any current Python; `uv tool install zem` still needs no Python at all.

## [0.9.10] - 2026-09-10
### Changed
- **Renamed Axonix → Zem.** Package `zem`, command `zem`, config at
  `~/.config/zem/config.json`, rc file `~/.zemrc`, history
  `~/.zem_history`, plugins/themes under `~/.zem/`, env vars
  `ZEM_CONFIG_PATH` / `ZEM_LOG_ENABLED` / `ZEM_LOG_LEVEL`. Existing
  Axonix files are moved to the new locations on first start.
- **Variable model.** `set NAME` now creates a shell-local variable; only
  exported variables (inherited from the environment, or promoted with
  `export`) reach child processes. Previously every `set` variable and
  even `?` leaked into children, and `unset` of an inherited variable was
  silently undone on the next line. Reassigning an inherited name such as
  `PATH` keeps it exported, so existing `~/.zemrc` files work unchanged.
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
- `config unset KEY`. `config set` validates the resulting document
  against the schema before writing, so a bad value (`input.path_depth
  -1`, duplicate operator symbols) is rejected instead of breaking the
  next start. All writers of `config.json` (`config set`, `theme set`,
  plugin default sync) go through one locked, atomic read-modify-write.
- fish-style ghost-text suggestions from history (`input.auto_suggest`,
  on by default).
- Job control: `&` detaches the whole pipeline as a job (`[1] pid`),
  Ctrl-Z stops the foreground job, `jobs [-l|-p]`, `fg`, `bg`, `wait`,
  `kill` (understands `%N`, sends SIGCONT to stopped jobs), `disown`.
  Job specs `%N`, `%%`, `%+`, `%-`, `%prefix`, pid. Finished jobs are
  reported before the next prompt; `exit` warns once about stopped jobs;
  remaining jobs get SIGHUP on exit.
- New builtins: `true`, `false`, `:`, `test`/`[` (file, string, integer
  tests, `!`, `-a`, `-o`, grouping), `type [-t]`, `command [-v|-V]`
  (plain `command CMD` bypasses aliases and builtins), `source`/`.`,
  `read [-r] [-s] [-p PROMPT] [NAME...]`, `printf` (`%s %d %i %o %x %X
  %f %e %g %c %%`, width/precision/flags, format reuse), `pushd`/`popd`/
  `dirs [-c]`, `eval`, `exec CMD`.
- Line continuation: a trailing `\`, an open quote or `$(`, or a
  trailing `|`/`&&`/`||` prompts for more input with `> `. Works in
  `~/.zemrc` too.
- History expansion `!!`, `!$`, `!N`, `!-N`, `!prefix` (unquoted, at word
  start; `!=` and a trailing `!` stay literal). The expanded line is
  echoed before running. Disable with `history.expand = false`.
- Command substitution `$(...)`, nested and quoted forms included. Output
  is word-split when unquoted and kept verbatim inside double quotes;
  `$?` is not affected by the substituted command.
- Parser: `~`, `~/path`, `~user/path` expansion (unquoted, also in
  redirect targets); stderr redirections `2>`, `2>>`, `2>&1`, `&>`, `&>>`.
  A missing redirect target is now a parse error instead of being
  silently ignored.
- `BaseCommand.execute` may declare `stderr=`; `_write_err()` helper.
- `ExecutionContext.set_var/unset_var/export_var/unexport_var/child_env`.
- `zem --version` / `zem -V` prints the installed version.
- `zem.__version__`, read from package metadata (single source of truth is
  `pyproject.toml`).
- GitHub Actions CI: ruff, mypy (non-blocking baseline), pytest on Linux and
  macOS.
- `Shell(user_plugins_dir=...)` / `load_plugins(user_plugins_dir=...)` so the
  external plugin directory can be redirected or disabled (used by tests).
- `BaseCommand.examples` is now a declared attribute shown by `help <command>`.
- Test fixtures: `full_shell` (real builtin registry, headless) and `run()`.

### Fixed
- `false; echo $?` printed the status of the *previous line*: the whole
  line was expanded before anything ran. Units are now expanded lazily,
  right before they execute.
- Path completion for arguments never worked (`ls som<TAB>`, `cd sr<TAB>`):
  the whole line was handed to the path completer as the path.
- Commands whose argument completer had nothing to offer (`git add <TAB>`)
  got no path completion either; now they fall back to paths.
- Command-name completion broke on `-` (`docker-com<TAB>` completed `com`).
- `|`, `;`, `&&` inside quotes started a new "command" for completion.
- Newly installed or venv binaries stayed highlighted as errors until
  `config reload`; the PATH scan is now cached per PATH value.
- A file created by the previous command was still underlined as missing.
- Ctrl-R search used hardcoded Dracula colours regardless of the theme.
- `yarn`/`pnpm` offered npm-only flags.
- Children inherited an ignored SIGTSTP/SIGTTIN/SIGTTOU/SIGQUIT from the
  shell and could not be suspended with Ctrl-Z.
- `a | b &` only detached `b`; `a` was still waited on.
- A variable whose value contained a quote (`set X "it's"; echo $X`) was
  mangled on expansion.
- Pipeline fds were closed twice in some error paths, which could close
  an unrelated descriptor that had reused the number.
- `AppConfig` read the config path once at class definition, so changing
  `ZEM_CONFIG_PATH` after import (or in tests) was ignored.
- Coloured builtins wrote CRLF line endings when redirected to a file.
- `echo a\'b` printed `ab`: the tokenizer dropped the backslash but kept
  the quote, which the quote-removal pass then treated as an opener.
- Builtin output was silently lost on `>` redirects and builtin-to-builtin
  pipes because the main thread and the worker thread closed the same file
  descriptor.
- First run with a missing config file crashed with `JSONDecodeError`.

### Removed
- The `add` test builtin is no longer shipped to users.
