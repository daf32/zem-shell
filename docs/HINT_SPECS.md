# Hint specs

Completion in Zem is declarative. A **hint spec** is a JSON file describing one
command — its subcommands, its flags, its positional arguments, and where the
values for each come from. One engine (`SpecCompleter`) runs every spec, so
teaching the shell about a new tool means writing JSON, not Python.

Specs live in two places:

| Location | Purpose |
|---|---|
| `src/zem/hints/data/*.json` | Shipped with Zem |
| `~/.zem/hints/*.json` | Yours |

A spec in your directory **replaces** the bundled one with the same `command`
(not merged — a half-merged tree of subcommands is impossible to debug). To
adjust a built-in spec, copy it and edit the copy. `ZEM_HINTS_PATH` takes a
colon-separated list of extra directories, searched in between.

A broken spec never breaks the shell: it is skipped, the rest keep working, and
the reason goes to the `zem.hints` logger (`ZEM_LOG_ENABLED=true`).

## A minimal spec

```json
{
  "schema_version": 1,
  "command": "hello",
  "description": "Greet someone",
  "subcommands": [
    {"name": "world", "description": "Greet the world"}
  ]
}
```

Save it as `~/.zem/hints/hello.json` and `hello <TAB>` offers `world`.

## The document

| Field | Meaning |
|---|---|
| `schema_version` | Required. Currently `1`. A spec from a newer schema is refused by name rather than half-understood. |
| `command` | The command this spec completes. |
| `aliases` | Other names it answers to (`pip.json` declares `pip3`). |
| `description` | One line, shown where the command itself is offered. |
| `fallback` | `files` (default), `dirs` or `none`: what to offer in a position the spec does not describe. |
| `options` | Flags. |
| `subcommands` | Nested commands, to any depth. |
| `args` | Positional arguments. |

`subcommands` entries take `name`, `aliases`, `description`, `hidden`, plus
their own `options`, `subcommands` and `args`.

### Options

```json
{"names": ["-U", "--upgrade"], "description": "Upgrade to the newest version"}
```

Every spelling of one flag goes in a single entry, so the description is written
once. Other fields:

- `value` — a value source. Absent means the flag takes no value;
  `{"type": "none"}` means it takes one we have nothing to suggest for.
- `repeatable` — the flag may appear more than once (`-e`, `-v`).
- `inherited` — visible in every nested subcommand (`git -C`, `docker --context`).
- `hidden` — parsed, never offered.

`--flag=value` and a short flag with its value glued on (`-p8080`) are both
understood, and `--` ends flag parsing.

### Positional arguments

```json
{"name": "pathspec", "description": "Files to stage",
 "source": {"type": "files"}, "variadic": true}
```

`args` is ordered. `variadic` means "and everything after this", and only the
last argument may be variadic. Flags and redirections do not shift the count:
in `git add --all > out.txt file`, `file` is still the first positional.

## Value sources

| Type | Offers |
|---|---|
| `values` | A fixed list. Items are strings or `{"value", "description"}`. |
| `files` | Paths. Optional `extensions` filter. |
| `dirs` | Directories only. |
| `commands` | Executables on `PATH`. |
| `none` | Nothing — and no path fallback either. |
| `command` | The stdout of an external command. |
| `provider` | A named Python function. |
| `any_of` | Several sources at once, in order. |

### `command`

```json
{"type": "command",
 "run": ["git", "for-each-ref", "--format=%(refname:short)\t%(contents:subject)",
         "refs/heads"],
 "parse": {"separator": "\t"},
 "timeout_ms": 300,
 "cache_ttl_ms": 2000,
 "cache_scope": "cwd",
 "guard": {"run": ["git", "rev-parse", "--is-inside-work-tree"]}}
```

`run` is an argv, never a shell string. Fields:

- `timeout_ms` (≤ 2000), after which the result is empty.
- `cache_ttl_ms` — how long to reuse the result. Completion fires on every
  keystroke; without a cache each letter would spawn a process.
- `cache_scope` — `cwd` (default) or `global` for results that do not depend on
  the directory (docker images, brew formulae).
- `accept_nonzero` — keep stdout even when the command failed.
- `min_prefix` — do not run until this many characters have been typed. For
  expensive searches.
- `guard` — a cheap precondition. Without one, `git for-each-ref` would run in
  every directory, repository or not.
- `parse` — `separator`, `value_column`, `description_column`, `skip_lines`,
  `max_items`.

**No interpolation.** `"run": ["git", "branch", "--list", "{word}"]` is rejected:
splicing what someone is typing into an argv is an injection vector. Values that
depend on the current input come from a provider, where the code is reviewable.
Go templates (`--format={{.Names}}`) are fine — doubled braces are not holes.

A command that fails, times out or does not exist yields no suggestions and no
message. A missing binary is remembered for a while, so a spec for a tool you
have not installed stops being probed.

### `provider`

```json
{"type": "provider", "name": "git.branches", "args": {"include_remotes": true}}
```

Names are namespaced (`git.*`, `docker.*`, `npm.*`, `zem.*`). Registering one:

```python
from zem.hints.providers import provider
from zem.hints.sources import Suggestion

@provider("mytool.targets")
def _targets(ctx):
    # ctx: cwd, shell, words, node_path, prefix, args
    return [Suggestion("all", "Build everything"), "clean"]
```

Return `Suggestion`, plain strings or `(value, description)` pairs — the engine
normalises them. A provider runs on a worker thread, so it must be thread-safe
and quick; an exception is swallowed into an empty list. Put the module in
`~/.zem/plugins/` and it is imported at startup, before completion happens.

Specs refer to providers **by name**, resolved at completion time, so a plugin
can supply values for a spec that already ships with Zem.

## Configuration

```
config set hints.enable false        # no specs at all
config set hints.dynamic false       # static parts only: nothing shells out
config set hints.cache_ttl_ms 5000
config set hints.command_timeout_ms 300
config set hints.user_dir ~/.zem/hints
```

## A note on trust

A spec can run a command when you press TAB. Installing someone else's spec is
the same act of trust as installing their plugin. The engine limits the damage —
argv only, never a shell; no interpolation of your input; a timeout; stdin from
/dev/null; its own session so a helper cannot grab the terminal — but it cannot
make an arbitrary command safe. Read a spec before you drop it in
`~/.zem/hints/`.

## Writing a Python completer instead

Some things a spec cannot express. `BaseArgCompleter` is still supported and
still wins over a bundled spec, so a builtin or plugin that implements
`get_completer()` keeps working — see `docs/COMMAND_DEVELOPMENT.md`.
