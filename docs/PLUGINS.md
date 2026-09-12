# Plugins

A plugin extends Zem with commands, completion, themes and hooks. There are
two shapes, and they are the same API:

- **A single file** in `~/.zem/plugins/` — for something you wrote for yourself.
- **A Python package** that declares a `zem.plugins` entry point — for
  something you distribute.

There is no separate plugin registry, and there does not need to be: a plugin
is code with dependencies, and PyPI already does that job.

## A plugin in one file

`~/.zem/plugins/greet.py`:

```python
from zem.builtins.base import BaseCommand
from zem.plugin import Plugin


class GreetCommand(BaseCommand):
    name = "greet"
    help = "Say hello"

    def execute(self, args, context, stdin=None, stdout=None, stderr=None):
        self._write(f"hello {' '.join(args) or 'world'}\n", stdout)
        return 0


class GreetPlugin(Plugin):
    version = "1.0.0"
    description = "Greets people"

    def commands(self):
        return [GreetCommand]
```

Restart Zem and `greet` is there. `plugin list` shows it.

A file that only declares `BaseCommand` subclasses, with no `Plugin` class,
still works — that is how plugins looked before this API — but it cannot be
disabled by name or carry a version.

## A plugin as a package

```toml
# pyproject.toml of your package
[project.entry-points."zem.plugins"]
weather = "zem_plugin_weather:WeatherPlugin"
```

Install it into the same environment as Zem:

```bash
uv tool install zem --with zem-plugin-weather
```

`uv` records the extra in its receipt, so the plugin survives
`uv tool upgrade zem`.

## What a plugin can provide

Every hook is optional.

| Hook | Returns |
|---|---|
| `commands()` | `BaseCommand` subclasses to register |
| `hint_specs()` | directories of completion specs (`*.json`) |
| `hint_providers()` | `{"mytool.things": fn}` — values for specs to use |
| `completers()` | `{"command": BaseArgCompleter}` for what a spec cannot express |
| `themes()` | directories of theme JSON files |

And four lifecycle hooks:

| Hook | When |
|---|---|
| `on_startup(shell)` | once, before the first prompt |
| `on_exit(shell)` | once, while shutting down |
| `pre_exec(line, shell)` | before each line; return a string to rewrite it |
| `post_exec(line, exit_code, shell)` | after each line |

`pre_exec` is the interesting one: returning a replacement rewrites what runs,
which is how a "did you mean" or an auto-`sudo` plugin would work. The first
plugin to return a rewrite wins. Keep it fast — it is on the path of every
command.

## Metadata

```python
class MyPlugin(Plugin):
    name = "mine"           # defaults to the class name minus "Plugin"
    version = "1.0.0"
    description = "One line, shown by `plugin list`"
    api_version = 1         # the API you wrote against
```

`api_version` is refused if it is newer than the shell understands, with a
message saying to upgrade Zem — better than half-loading something that
expects hooks which do not exist.

## Managing plugins

```
plugin list              what was found, where from, and whether it loaded
plugin info <name>       version, source, and what it provides
plugin install <pkg>     install a plugin package
plugin remove <pkg>      uninstall it
plugin packages          installed packages that provide plugins
plugin disable <name>    stop loading it
plugin enable <name>     load it again
```

`plugin install` works out how Zem itself was installed and uses the matching
command — `uv tool install`, `pipx inject`, or `pip install` into the same
interpreter — because installing into the wrong one means Zem never sees the
plugin. It prints the exact command and asks before running it; `-y` skips the
question, and without a terminal to ask on it refuses rather than guessing.

One detail worth knowing if you use `uv`: `uv tool install --with` *replaces*
the extras rather than adding to them, so `plugin install` reads what is
already there and passes it again. Installing a second plugin by hand with a
bare `uv tool install zem --with new-one` would quietly uninstall the first.

Disabling writes to `disabled_plugins` in `config.json` and takes effect on
the next start: a command registers itself when its module is imported, so the
only way not to have it is not to import it.

## When a plugin misbehaves

One broken plugin never stops the shell. An import that raises, a hook that
raises, a version from the future — each is recorded against that plugin and
the rest carry on. `plugin list` marks it `failed` and `plugin info` prints the
error. Set `ZEM_LOG_ENABLED=true` for the full traceback path.

The flip side: a plugin is code you are running in your shell, with your
permissions, on every command. Install one the way you would install anything
else from PyPI — knowing whose it is.

## Configuration

Ship defaults with `get_default_config()` on a command; the shell writes them
into `config.json` under `plugins.<name>` on first start, and
`self.get_plugin_config(context)` reads them back. See
`docs/COMMAND_DEVELOPMENT.md`.
