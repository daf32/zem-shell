# The prompt

The prompt is a **format string** naming the modules it is made of:

```bash
config set prompt.format '$venv$exit_code$path$git$symbol'
config set prompt.right_format '$duration$time'
```

## The format language

| Construct | Meaning |
|---|---|
| `$name`, `${name}` | a module (or, inside a module's format, one of its variables) |
| `[text](style)` | styles what it contains; these nest |
| `(...)` | renders only if something inside produced output |
| `\$ \[ \] \( \)` | a literal `$`, bracket or parenthesis |

The conditional group is what keeps punctuation honest. With

```
$path( on $git)$symbol
```

you get `~/project on (main*) #` inside a repository and `~/project #`
outside it — the word "on" leaves with the branch, rather than dangling.

## Configuring a module

Each module has its own section under `prompt.modules`, with `format`,
`style` and `disabled`:

```bash
config set prompt.modules '{"git": {"format": " on [$branch$status](bold magenta)"},
                            "venv": {"disabled": true}}'
```

Inside a module's format, `$style` means "this module's style", so you can
change the colour without rewriting the layout:

```bash
config set prompt.modules '{"path": {"style": "fg:#ff8800"}}'
```

A style is either a theme colour key (`path`, `git_branch`, `error` — these
follow the active theme) or a literal prompt_toolkit style (`bold green`,
`fg:#ff8800`, `bg:blue fg:white underline`).

## The modules that ship

| Module | Variables | Shows |
|---|---|---|
| `venv` | `$name` | the active virtualenv |
| `exit_code` | `$code` | the last exit status, green or red |
| `path` | `$path` | the working directory, shortened |
| `git` | `$branch`, `$status` | branch and dirty marker, inside a repo |
| `symbol` | `$symbol` | the prompt character |
| `jobs` | `$count` | how many background jobs, when there are any |
| `user`, `host` | `$user`, `$host` | who and where |
| `duration` | `$duration` | how long the last command took, past 100 ms |
| `time` | `$time` | the clock (`prompt.time_format`) |

A module renders nothing when it has nothing to say: no virtualenv, not a
repository, no background jobs, a command too fast to time.

## Examples

```bash
# two lines, with a box drawing
config set prompt.format '┌─ $user@$host $path$git
└─ $symbol'

# minimal
config set prompt.format '$path$symbol'

# starship-ish
config set prompt.format '$path( on [$git](bold purple)) $symbol'
```

## When something is wrong

A format string that does not parse, a module name that does not exist, a
module that raises — each costs that piece and nothing else; the prompt
still renders. Run with `ZEM_LOG_ENABLED=true` to see why.
