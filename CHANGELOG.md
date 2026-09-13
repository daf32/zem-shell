# Changelog

All notable changes to Zem are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]
### Fixed
- **A failed `&&` no longer swallows the rest of the line.** `make && ./run;
  cleanup` now runs `cleanup` when `make` fails, `false && a; b` runs `b`,
  and `true || a && b` runs `b` — bash's rule, applied left to right: a
  command that does not run leaves the status alone, so the next operator
  is judged against the same one. Every case in the new test table was
  taken from `bash -c`.
  A skipped command is not expanded either, so `false && echo $(rm -rf x)`
  never starts the substitution — which is exactly what the old
  stop-the-line behaviour was accidentally protecting.

## [0.12.11] - 2026-09-13
### Changed
- **A command that cannot be found now exits with 127**, the code every
  other shell uses and the one scripts test for. It used to exit with 2,
  which is what a command that *was* found and used wrongly returns.
- **A command that fails no longer ends the line.** `nosuchcmd || echo
  fallback` now runs the fallback, `nosuchcmd; echo next` still echoes,
  and `echo $(nosuchcmd)` reports the failure and echoes an empty
  substitution — all as in bash. The error used to abort everything after
  it, which made the status impossible to act on. A syntax error still
  ends the line.
- **`operators.and_if`, `operators.or_if` and `operators.space` are
  retired.** They sat in every `config.json` without being read: `&&` is
  the `background` operator twice, `||` is `pipe` twice, and words are
  split on any whitespace. zem wrote those keys itself, so it now says
  they can be deleted rather than calling them unknown.
- **The bundled `weather` plugin was rewritten as the example it is meant
  to be**: it returns an exit code, reports failures on stderr (so
  `weather || echo offline` works), names what went wrong instead of
  catching everything, takes `timeout_s` alongside `default_city`, and is
  a real `Plugin`, so `plugin list` shows it and `plugin disable weather`
  works. Ctrl-C during a slow request now ends the command.

### Removed
- Dead code: `zem/utils/colors.py` (only the error prefix was used, and it
  ignored the configuration it was handed), `ThemeManager.has_light_variant`
  / `has_dark_variant`, `CommandFailedError`, `ConfigNotFoundError` and
  `ShellEnvironmentError`, and the unused singleton on `CommandRegistry`.

## [0.12.10] - 2026-09-13
### Fixed
- **The git part of the prompt showed `+` for a branch that was behind its
  upstream and `-` for one that was ahead** — the two counts were read the
  wrong way round.
- A detached HEAD showed the word `HEAD`; it now shows the short commit.

### Changed
- **The prompt asks git once instead of six times.** A single
  `git status --porcelain=v2 --branch` answers branch, ahead/behind and
  dirty, which takes ~11 ms where the six calls took ~60 ms, and it is
  isolated like the completion helpers are: its own session (a git helper
  can no longer take the terminal and hang the prompt), no stdin, and
  `GIT_OPTIONAL_LOCKS=0`, so drawing a prompt never touches
  `.git/index.lock` while you are running git in that repository.
- The `git` prompt module takes `timeout_ms` (default 1000) and
  `max_length` (default 20) under `prompt.modules.git`. The old code gave
  each of its six calls half a second, so a slow repository could hold the
  prompt for three.

## [0.12.9] - 2026-09-13
### Security
- **`theme import` and `theme install` can no longer write outside
  `~/.zem/themes/`.** The file name came from the theme's own `name` field
  unchecked, so a theme calling itself `../../x` was written to `~/x.json`.
  Names are now normalised (`My Theme` becomes `my_theme`) and limited to
  letters, digits, `_` and `-`; the theme is validated before it is
  written, and the command says what was wrong instead of "failed".
- **Only `https://` URLs are fetched** by `theme install` and by the hint
  spec registry (`hints search|install|update`); plain `http://` is accepted
  for `localhost` only. Over http the SHA-256 in the index protected
  against nothing, and `file://` would have read any file. Downloads are
  also capped in size.

### Changed
- **Unknown keys in `config.json` are reported.** A misspelt key was
  silently ignored; the shell now prints `warning: config.json: unknown key
  'histroy' is ignored` at startup, and `config set` refuses a key the
  schema does not know instead of writing it. Free-form sections
  (`plugins.*`, `prompt.modules.*`) are unaffected.

## [0.12.8] - 2026-09-13
### Fixed
- **Ctrl-C now interrupts a builtin** (`read`, `weather`, `prompt configure`,
  `plugin install`, a `$(...)` being collected) with exit status 130. Before,
  the command kept running and, worse, the next line typed at the prompt was
  silently dropped.
- **A `PROMPT` or `INPUT` variable in the parent shell no longer stops zem
  from starting.** Configuration is read from the environment only under a
  `ZEM_` prefix (`ZEM_ACTIVE_THEME=nord zem`); bare section names used to be
  parsed as JSON.
- Plugins' `on_exit` hook ran twice when the shell was terminated with
  SIGTERM.

### Changed
- **One history.** The arrow keys, Ctrl-R, `!!` and the `history` command
  now share the same entries: the file is read at startup
  (`history.load_on_start`), `history` lists previous sessions too, and the
  file is trimmed to `history.max_entries` on exit (`history.rotate`).
  `history.save_on_exit: false` keeps a session's history in memory only.
  These three keys existed but did nothing.
- `~/.zem_history` is created readable by its owner only (0600), like bash's;
  an existing file keeps its permissions.

### Added
- `tests/interactive/`: the shell driven in a real pseudo-terminal through
  pexpect (Ctrl-C, Ctrl-Z, `fg`/`bg`, `exit`, termios restore, SIGHUP to
  jobs, history across sessions). Runs with the rest of the suite.

## [0.12.7] - 2026-09-13
### Fixed
- **Parser conformance with POSIX** in the idioms people carry over from
  bash. A backslash inside double quotes now escapes only `$`, `"`, `\`,
  `` ` `` and a newline, so `printf "%s\n"` prints newlines instead of the
  letter `n` and `"C:\temp"` keeps its backslash. `# comment` at the end of
  a line is a comment (also in `~/.zemrc` after a command), and a `|` or `;`
  inside one no longer starts a command. A single `&` ends the command it
  follows, so `sleep 5 & echo hi` runs both instead of handing `echo hi` to
  `sleep`. An alias body is re-parsed as text, the way bash does it:
  `alias gl='git log --oneline | head'` and `alias up='git pull && uv sync'`
  work, an alias in a later pipeline stage (`... | up`) expands, and a
  quoted first word (`'ls'`, `\ls`) bypasses the alias.
- An unset (or empty) variable used unquoted expands to nothing: `ls $UNSET`
  runs `ls`, not `ls ''`. In double quotes it still gives an empty argument.

### Added
- Special parameters `$$` (the shell's pid), `$!` (pid of the last
  background job), `$0` (`zem`), `$#`, `$@` and `$*` (empty: scripts take no
  arguments yet).
- `tests/test_parser_conformance.py`: a corpus of lines whose argv was
  checked against bash, plus the one deliberate difference (`$VAR` is not
  word-split).

## [0.12.6] - 2026-09-13
### Changed
- **`help` ships as a plugin**, finishing the split. Zem is now built out of
  its own plugin API: nine bundled plugins (`coreutils`, `scripting`,
  `dirstack`, `history`, `help`, `theme`, `logo`, `venv`, `weather`), all on
  by default and all removable with `plugin disable`. What stays in the core
  is the parser, the executor, job control, the variable model, `cd`/`pwd`/
  `exit`, `alias`/`unalias`, and the four commands that manage the shell
  itself (`config`, `plugin`, `hints`, `prompt`) — disable those and there
  would be no way back.
- The fallback `~/.zemrc` no longer writes `alias help='help'`, an alias of
  a command to itself that did nothing.


## [0.12.5] - 2026-09-13
### Changed
- **`pushd`, `popd`, `dirs` ship as the `dirstack` plugin**, and **`history`
  as `history`**. Both are on by default. Recording history, `!!` expansion
  and Ctrl-R searching stay in the core — the plugin is only the command
  that lists and prunes it; the directory stack itself lives on the
  execution context, so disabling the plugin removes the commands, not the
  data.


## [0.12.4] - 2026-09-13
### Changed
- **`echo`, `printf`, `test`, `[`, `true`, `false`, `:` ship as the
  `coreutils` plugin**, and **`source`, `.`, `eval`, `exec`, `read`,
  `command`, `type` as `scripting`**. Both are on by default and behave
  exactly as before; `plugin disable coreutils` gives you `/bin/echo` and
  `/bin/test` instead, and the shell keeps working. `command CMD` forcing an
  external lookup is parser behaviour and does not depend on the plugin.


## [0.12.3] - 2026-09-13
### Changed
- **`theme`, `logo` and `venv` ship as plugins** rather than as builtins, so
  `plugin list` shows them and `plugin disable theme` removes the command and
  the bundled themes together. The core keeps what a shell cannot do without:
  the parser, the executor, job control, the variable model, `cd`, `pwd`,
  `exit`, `set`/`unset`/`export`/`get`, the job-control commands, and
  `config`/`plugin` — turn those off and there would be no way back.
- A plugin may now be a package, not just a single module, which is how a
  plugin ships data alongside its code.
- The default `~/.zemrc` calls `logo 2>/dev/null || true`, so disabling the
  logo plugin does not produce an error on every start. Existing rc files are
  not touched; edit the line yourself if you disable it.


## [0.12.2] - 2026-09-13
### Added
- **`prompt` command**: `prompt list` draws every preset, `prompt set pure`
  switches to one, `prompt configure` asks a few questions with previews
  after each, and `prompt reset` goes back to the default. Six presets ship
  (`classic`, `minimal`, `pure`, `powerline`, `two_line`, `verbose`); your
  own go in `~/.zem/prompts/`. Previews use made-up values, so a preset
  looks the same wherever you run it from.

### Fixed
- CI refuses a change that writes into an already-released CHANGELOG
  section, which is what happens when a branch is rebased across someone
  else's release.


## [0.12.1] - 2026-09-13
### Fixed
- `>&2` no longer creates a file named `&`. The parser understands file
  descriptor duplication in its general `N>&M` form, so `echo oops >&2`,
  `cmd 1>&2` and the self-duplications `>&1` / `2>&2` behave like they do in
  bash; only `2>&1` used to be recognised. A descriptor other than 1 or 2
  (`>&3`) is now a parse error instead of a stray file.
- Error messages are escaped before they are rendered, so one quoting the
  offending line (`1>&2`, `a<b`) prints instead of crashing the shell.

## [0.12.0] - 2026-09-13
### Added
- **The prompt is a format string**, in the spirit of Starship:
  `config set prompt.format '$venv$exit_code$path$git$symbol'`, with
  `prompt.right_format` for the right-hand side. `$module` substitutes a
  module, `[text](style)` styles what it contains, and `(...)` renders only
  when something inside it produced output — so `$path( on $git)$symbol`
  loses the word "on" along with the branch outside a repository. Each
  module is configurable under `prompt.modules` with its own `format`,
  `style` and `disabled`, and a style is either a theme colour key or a
  literal like `bold green` / `fg:#ff8800`. New modules: `user`, `host`,
  `jobs`. See `docs/PROMPT.md`.
- Plugins contribute prompt modules through `prompt_modules()` — a module
  reports variables and its format decides how they are shown, so users can
  restyle a plugin's module without touching its code.
- Plugins can add key bindings through `key_bindings()`; the shell's own are
  merged first, so `Ctrl-C` and `Ctrl-R` cannot be taken away by accident.

### Fixed
- The uncoloured prompt (`input.color_prompt = false`) matches the coloured
  one. It was a second, separate implementation: it printed the literal
  `None` when no virtualenv was active, and ran the venv name straight into
  the path without the brackets the coloured prompt used.


## [0.11.3] - 2026-09-12
### Added
- `plugin install` / `plugin remove` / `plugin packages`. Installing detects
  how Zem itself was installed (`uv tool`, `pipx`, or a virtualenv) and runs
  the matching command, showing it and asking first — `-y` skips the question,
  and with no terminal to ask on it refuses instead of guessing. Under `uv` it
  re-passes the extras already installed, since `uv tool install --with`
  replaces rather than adds.


## [0.11.2] - 2026-09-12
### Added
- **Plugin API.** A plugin is a `Plugin` subclass — a single file in
  `~/.zem/plugins/` or a package declaring a `zem.plugins` entry point
  (`uv tool install zem --with your-plugin`). It can contribute commands,
  completion hint specs, value providers, Python completers and themes, and
  hook into `on_startup`, `on_exit`, `pre_exec` (which may rewrite the line)
  and `post_exec`. `plugin list|info|enable|disable` manages them, and
  `disabled_plugins` in the config records what is off. Plugins that only
  declared commands, with no `Plugin` class, keep working unchanged. See
  `docs/PLUGINS.md`.
- One broken plugin no longer risks the shell: a failing import, a failing
  hook or an `api_version` from the future is recorded against that plugin
  and everything else loads.


## [0.11.1] - 2026-09-12
### Added
- **Non-interactive mode.** `zem -c "command"` runs one command and exits with
  its status, `zem script.zem` runs a file, and a script piped into `zem` is
  read from stdin — so the shell can be used from a Makefile, a git hook or
  CI. `~/.zemrc` is skipped in these modes (as in bash, zsh and fish) unless
  `--rc` is passed. `zem --help` describes all of it.

### Fixed
- An unknown command-line option is an error instead of being ignored:
  `zem --hepl` used to swallow the flag and open a session.


## [0.11.0] - 2026-09-12
### Added
- **`hints` command and a spec registry.** The wheel ships specs only for
  tools almost everyone has; the rest are fetched on demand with
  `hints search` / `hints install` / `hints update` / `hints remove`, which
  verify each download's checksum and validate it before writing to
  `~/.zem/hints/`. `hints list`, `hints show <command>`, `hints validate` and
  `hints providers` cover inspection and writing your own. The default
  registry is [daf32/zem-hints](https://github.com/daf32/zem-hints); point
  `hints.registry_url` at your own if you like.

### Changed
- Specs for `kubectl`, `brew`, `gh` and `go` no longer ship in the wheel:
  they live in the [spec registry](https://github.com/daf32/zem-hints) and
  install on demand, so they reach you without waiting for a Zem release.

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
  (`kubectl`, `brew`, `gh` and `go` moved to the registry in 0.11.0.)
- Completion now runs on a worker thread, so a spec that shells out cannot
  stall the prompt.
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
