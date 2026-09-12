"""The plugin API: discovery, hooks, failure handling, and `plugin`."""

import textwrap

import pytest

from zem.config.settings import AppConfig
from zem.core.shell import Shell
from zem.plugin import PLUGIN_API_VERSION, Plugin, PluginManager

DEMO = '''
from zem.builtins.base import BaseCommand
from zem.plugin import Plugin


class GreetCommand(BaseCommand):
    name = "greet"
    help = "Say hello"

    def execute(self, args, context, stdin=None, stdout=None, stderr=None):
        self._write("hello " + (" ".join(args) or "world") + "\\n", stdout)
        return 0


class DemoPlugin(Plugin):
    version = "1.2.3"
    description = "A demo plugin"

    def commands(self):
        return [GreetCommand]

    def hint_providers(self):
        return {"demo.colours": lambda ctx: ["red", "green"]}

    def on_startup(self, shell):
        shell.context.variables["DEMO_STARTED"] = "1"

    def on_exit(self, shell):
        shell.context.variables["DEMO_EXITED"] = "1"

    def post_exec(self, line, exit_code, shell):
        shell.context.variables["DEMO_LAST"] = str(exit_code)
'''


@pytest.fixture
def plugin_dir(tmp_path, monkeypatch):
    """A directory of single-file plugins, importable and disposable."""
    directory = tmp_path / "plugins"
    directory.mkdir()

    def _write(name, source):
        (directory / f"{name}.py").write_text(textwrap.dedent(source))
        # Modules are cached by name; a fresh test must not see the old one.
        import sys

        sys.modules.pop(name, None)
        return directory

    _write.path = directory
    yield _write

    import sys

    for path in directory.glob("*.py"):
        sys.modules.pop(path.stem, None)


@pytest.fixture
def plugin_shell(plugin_dir, isolated_config):
    def _build(config=None):
        return Shell(
            commands=None,
            config=config or isolated_config,
            headless=True,
            user_plugins_dir=str(plugin_dir.path),
        )

    return _build


def test_single_file_plugin_is_found(plugin_dir, plugin_shell):
    plugin_dir("demo", DEMO)
    shell = plugin_shell()
    record = next(r for r in shell.plugins.loaded if r.name == "demo")
    assert record.origin == "user" and record.version == "1.2.3" and not record.error


def test_plugin_command_is_registered(plugin_dir, plugin_shell, run):
    plugin_dir("demo", DEMO)
    shell = plugin_shell()
    code, out, _ = run(shell, "greet there")
    assert code == 0 and out.strip() == "hello there"


def test_startup_and_post_exec_hooks(plugin_dir, plugin_shell, run):
    plugin_dir("demo", DEMO)
    shell = plugin_shell()
    assert shell.context.variables["DEMO_STARTED"] == "1"
    run(shell, "false")
    assert shell.context.variables["DEMO_LAST"] == "1"


def test_hint_provider_from_a_plugin(plugin_dir, plugin_shell):
    from zem.hints.providers import PROVIDERS

    plugin_dir("demo", DEMO)
    plugin_shell()
    assert PROVIDERS.get("demo.colours") is not None


def test_pre_exec_can_rewrite_the_line(plugin_dir, plugin_shell, run):
    plugin_dir("rewrite", '''
        from zem.plugin import Plugin

        class RewritePlugin(Plugin):
            def pre_exec(self, line, shell):
                return line.replace("sudo ", "") if line.startswith("sudo ") else None
    ''')
    shell = plugin_shell()
    code, out, _ = run(shell, "sudo echo unprivileged")
    assert code == 0 and out.strip() == "unprivileged"


def test_a_broken_plugin_does_not_stop_the_shell(plugin_dir, plugin_shell, run):
    plugin_dir("broken", "raise RuntimeError('boom')")
    plugin_dir("demo", DEMO)
    shell = plugin_shell()
    broken = next(r for r in shell.plugins.loaded if r.name == "broken")
    assert "boom" in broken.error
    # The healthy one still works.
    assert run(shell, "greet")[0] == 0


def test_a_hook_that_raises_is_contained(plugin_dir, plugin_shell, run):
    plugin_dir("grumpy", '''
        from zem.plugin import Plugin

        class GrumpyPlugin(Plugin):
            def commands(self):
                raise ValueError("no commands for you")

            def post_exec(self, line, exit_code, shell):
                raise ValueError("nor hooks")
    ''')
    shell = plugin_shell()
    record = next(r for r in shell.plugins.loaded if r.name == "grumpy")
    assert "no commands for you" in record.error
    assert run(shell, "true")[0] == 0  # the shell keeps going


def test_a_plugin_from_the_future_is_refused(plugin_dir, plugin_shell):
    plugin_dir("futuristic", f'''
        from zem.plugin import Plugin

        class FuturePlugin(Plugin):
            api_version = {PLUGIN_API_VERSION + 1}
    ''')
    shell = plugin_shell()
    record = next(r for r in shell.plugins.loaded if r.name == "futuristic")
    assert "upgrade zem" in record.error


def test_old_style_module_still_works(plugin_dir, plugin_shell, run):
    """A file that only declares a BaseCommand, with no Plugin class."""
    plugin_dir("oldstyle", '''
        from zem.builtins.base import BaseCommand

        class LegacyCommand(BaseCommand):
            name = "legacy"
            help = "Old style"

            def execute(self, args, context, stdin=None, stdout=None):
                self._write("still here\\n", stdout)
                return 0
    ''')
    shell = plugin_shell()
    assert run(shell, "legacy")[1].strip() == "still here"


def test_bundled_plugins_are_listed(plugin_shell):
    shell = plugin_shell()
    assert any(r.name == "weather" and r.origin == "bundled" for r in shell.plugins.loaded)


def test_disabled_plugin_is_not_loaded(plugin_dir, plugin_shell, isolated_config):
    plugin_dir("demo", DEMO)
    isolated_config.disabled_plugins = ["demo"]
    shell = plugin_shell(isolated_config)
    record = next(r for r in shell.plugins.loaded if r.name == "demo")
    assert not record.enabled and record.plugin is None
    assert "greet" not in shell.commands


def test_entry_point_plugins(monkeypatch, isolated_config):
    """Packages advertise themselves through the `zem.plugins` group."""
    class PackagedPlugin(Plugin):
        name = "packaged"
        version = "2.0.0"
        description = "From an entry point"

    class FakeEntryPoint:
        name = "packaged"
        value = "some_package:PackagedPlugin"

        def load(self):
            return PackagedPlugin

    monkeypatch.setattr(
        "zem.plugin.manager.importlib.metadata.entry_points",
        lambda group=None: [FakeEntryPoint()],
    )
    manager = PluginManager(user_plugins_dir=None)
    manager.discover()
    record = next(r for r in manager.loaded if r.name == "packaged")
    assert record.origin == "entry_point" and record.version == "2.0.0"


def test_a_broken_entry_point_is_contained(monkeypatch):
    class FakeEntryPoint:
        name = "explosive"
        value = "nope:Nope"

        def load(self):
            raise ImportError("no such package")

    monkeypatch.setattr(
        "zem.plugin.manager.importlib.metadata.entry_points",
        lambda group=None: [FakeEntryPoint()],
    )
    manager = PluginManager(user_plugins_dir=None)
    manager.discover()
    record = next(r for r in manager.loaded if r.name == "explosive")
    assert "no such package" in record.error


# -- the `plugin` command --------------------------------------------------

def test_plugin_list(plugin_dir, plugin_shell, run):
    plugin_dir("demo", DEMO)
    code, out, _ = run(plugin_shell(), "plugin list")
    assert code == 0 and "demo" in out and "A demo plugin" in out


def test_plugin_info(plugin_dir, plugin_shell, run):
    plugin_dir("demo", DEMO)
    code, out, _ = run(plugin_shell(), "plugin info demo")
    assert code == 0
    assert "1.2.3" in out and "GreetCommand" in out and "demo.colours" in out


def test_plugin_info_unknown(plugin_shell, run):
    code, _, err = run(plugin_shell(), "plugin info nope")
    assert code == 1 and "not found" in err


def test_plugin_disable_and_enable_write_the_config(plugin_dir, plugin_shell, run):
    from zem.config.settings import get_config_path
    from zem.config.store import read_raw

    plugin_dir("demo", DEMO)
    shell = plugin_shell()
    code, out, _ = run(shell, "plugin disable demo")
    assert code == 0 and "restart" in out
    assert read_raw(get_config_path())["disabled_plugins"] == ["demo"]
    assert shell.config.disabled_plugins == ["demo"]

    run(shell, "plugin enable demo")
    assert read_raw(get_config_path())["disabled_plugins"] == []


def test_plugin_disable_unknown(plugin_shell, run):
    code, _, err = run(plugin_shell(), "plugin disable nope")
    assert code == 1 and "not found" in err


def test_plugin_unknown_subcommand(plugin_shell, run):
    code, _, err = run(plugin_shell(), "plugin frobnicate")
    assert code == 2 and "unknown subcommand" in err


def test_config_rejects_a_bad_disabled_list(isolated_config):
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        AppConfig(disabled_plugins="notalist")
