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


# -- installing ------------------------------------------------------------

@pytest.fixture
def installer(monkeypatch):
    """Record installer commands instead of running them."""
    from zem.plugin import installer as module

    calls = []

    def _install(kind="uv-tool", extras=(), returncode=0, can_install=True, reason=""):
        monkeypatch.setattr(
            module, "detect_environment",
            lambda: module.Environment(kind, f"{kind} (test)", can_install, reason),
        )
        monkeypatch.setattr(module, "uv_tool_extras", lambda: list(extras))

        def _run(command, stdout=None, stderr=None):
            calls.append(list(command))
            return returncode

        monkeypatch.setattr(module, "run", _run)
        # Confirmation reads the real stdin otherwise.
        monkeypatch.setattr("sys.stdin", type("T", (), {"isatty": lambda self: True})())
        return calls

    _install.calls = calls
    return _install


def test_install_keeps_the_extras_already_there(plugin_shell, run, installer):
    """`uv tool install` replaces the extras rather than adding to them, so
    the ones already installed must be passed again."""
    calls = installer(kind="uv-tool", extras=["zem-plugin-a", "zem-plugin-b"])
    code, out, _ = run(plugin_shell(), "plugin install -y zem-plugin-c")
    assert code == 0, out
    assert calls == [[
        "uv", "tool", "install", "zem",
        "--with", "zem-plugin-a", "--with", "zem-plugin-b", "--with", "zem-plugin-c",
    ]]
    assert "restart zem" in out


def test_remove_drops_only_the_named_one(plugin_shell, run, installer):
    calls = installer(kind="uv-tool", extras=["zem-plugin-a", "zem-plugin-b"])
    code, _, _ = run(plugin_shell(), "plugin remove -y zem-plugin-a")
    assert code == 0
    assert calls == [[
        "uv", "tool", "install", "zem", "--reinstall", "--with", "zem-plugin-b",
    ]]


def test_pipx_uses_inject(plugin_shell, run, installer):
    calls = installer(kind="pipx")
    run(plugin_shell(), "plugin install -y zem-plugin-c")
    assert calls == [["pipx", "inject", "zem", "zem-plugin-c"]]


def test_venv_uses_pip(plugin_shell, run, installer):
    import sys

    calls = installer(kind="venv")
    run(plugin_shell(), "plugin install -y zem-plugin-c")
    assert calls == [[sys.executable, "-m", "pip", "install", "zem-plugin-c"]]


def test_system_python_is_refused_with_a_reason(plugin_shell, run, installer):
    calls = installer(kind="system", can_install=False, reason="running from a system Python")
    code, _, err = run(plugin_shell(), "plugin install -y zem-plugin-c")
    assert code == 1 and "system Python" in err
    assert calls == []


def test_a_failing_installer_is_reported(plugin_shell, run, installer):
    installer(kind="venv", returncode=2)
    code, _, err = run(plugin_shell(), "plugin install -y zem-plugin-c")
    assert code == 2 and "exited with 2" in err


@pytest.mark.parametrize("bad", ["rm -rf /", "../evil", "https://example.com/x.whl", "a;b"])
def test_only_package_names_are_accepted(plugin_shell, run, installer, bad):
    calls = installer(kind="venv")
    code, _, err = run(plugin_shell(), f"plugin install -y '{bad}'")
    assert code == 2 and "does not look like a package name" in err
    assert calls == []


@pytest.mark.parametrize("good", ["zem-plugin-x", "zem_plugin_x", "zem-plugin-x==1.2.3",
                                  "zem-plugin-x[extra]", "zem-plugin-x>=1.0"])
def test_ordinary_requirements_are_accepted(good):
    from zem.plugin.installer import validate

    validate([good])


def test_install_without_a_terminal_needs_yes(plugin_shell, run, installer, monkeypatch):
    calls = installer(kind="venv")
    monkeypatch.setattr("sys.stdin", type("T", (), {"isatty": lambda self: False})())
    code, _, err = run(plugin_shell(), "plugin install zem-plugin-c")
    assert code == 1 and "pass -y" in err
    assert calls == []


def test_uv_extras_are_parsed_from_uv_output(monkeypatch):
    import subprocess as sp

    from zem.plugin import installer as module

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: sp.CompletedProcess(
        a[0], 0, "ruff v0.1.0\nzem v0.11.1 [with: pyfiglet, cowsay]\n", ""))
    assert module.uv_tool_extras() == ["pyfiglet", "cowsay"]


def test_uv_extras_when_there_are_none(monkeypatch):
    import subprocess as sp

    from zem.plugin import installer as module

    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: sp.CompletedProcess(
        a[0], 0, "zem v0.11.1\n", ""))
    assert module.uv_tool_extras() == []


def test_environment_detection_reads_the_prefix(tmp_path, monkeypatch):
    from zem.plugin import installer as module

    monkeypatch.setattr("sys.prefix", str(tmp_path))
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}")

    (tmp_path / "uv-receipt.toml").write_text("[tool]\n")
    assert module.detect_environment().kind == "uv-tool"

    (tmp_path / "uv-receipt.toml").unlink()
    (tmp_path / "pipx_metadata.json").write_text("{}")
    assert module.detect_environment().kind == "pipx"


def test_detection_without_the_installer_on_path(tmp_path, monkeypatch):
    from zem.plugin import installer as module

    monkeypatch.setattr("sys.prefix", str(tmp_path))
    (tmp_path / "uv-receipt.toml").write_text("[tool]\n")
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    environment = module.detect_environment()
    assert not environment.can_install and "not on PATH" in environment.reason
