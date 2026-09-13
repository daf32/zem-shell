"""The prompt, as segments."""

import pytest

from zem.ui.prompt import (
    PromptContext,
    PromptRenderer,
    PromptSegment,
    format_duration,
    format_path,
)


@pytest.fixture
def ctx(full_shell, tmp_path):
    full_shell.config.input.show_venv_info = False
    full_shell.config.input.show_git_info = False
    return PromptContext(shell=full_shell, cwd=str(tmp_path), exit_code=0)


@pytest.fixture
def renderer(full_shell):
    return PromptRenderer(full_shell)


def test_default_order(renderer, ctx):
    fragments = renderer.render(ctx.shell.config.input.segments, ctx)
    assert [style for style, _ in fragments] == [
        "class:exit_code_ok", "class:path", "", "class:prompt_symbol", "",
    ]


def test_exit_code_colour_follows_the_status(renderer, ctx):
    assert renderer.render(["exit_code"], ctx)[0][0] == "class:exit_code_ok"
    ctx.exit_code = 1
    assert renderer.render(["exit_code"], ctx)[0][0] == "class:exit_code_err"


def test_segments_can_be_reordered(renderer, ctx):
    fragments = renderer.render(["symbol", "path"], ctx)
    assert fragments[0][0] == ""  # the symbol's leading space
    assert fragments[-1][0] == "class:path"


def test_a_segment_with_nothing_to_say_is_skipped(renderer, ctx):
    ctx.shell.config.input.show_exit_code = False
    assert renderer.render(["exit_code"], ctx) == []


def test_venv_and_git_respect_their_settings(renderer, ctx, monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/some-venv")
    ctx.shell.config.input.show_venv_info = False
    assert renderer.render(["venv"], ctx) == []
    ctx.shell.config.input.show_venv_info = True
    assert renderer.render(["venv"], ctx)[0][1] == "[some-venv] "


def test_duration_below_the_threshold_is_not_shown(renderer, ctx):
    ctx.duration = 0.01
    assert renderer.render(["duration"], ctx) == []
    ctx.duration = 1.25
    assert renderer.render(["duration"], ctx)[0][1] == "⏱ 1.2s "


def test_plain_text_mode_is_the_same_segments(renderer, ctx):
    coloured = renderer.render(["exit_code", "path", "symbol"], ctx)
    plain = renderer.render(["exit_code", "path", "symbol"], ctx, colored=False)
    assert plain == "".join(text for _style, text in coloured)


def test_an_unknown_segment_is_skipped(renderer, ctx, caplog):
    # A typo in the config must cost that segment, not the prompt.
    fragments = renderer.render(["exit_code", "nosuchsegment", "symbol"], ctx)
    assert [style for style, _ in fragments] == [
        "class:exit_code_ok", "", "class:prompt_symbol", "",
    ]


def test_a_segment_that_raises_is_contained(renderer, ctx):
    class Exploding(PromptSegment):
        name = "boom"

        def render(self, ctx):
            raise RuntimeError("no prompt for you")

    renderer.segments["boom"] = Exploding()
    fragments = renderer.render(["boom", "symbol"], ctx)
    assert [style for style, _ in fragments] == ["", "class:prompt_symbol", ""]


def test_a_plugin_segment_can_replace_a_builtin(full_shell, ctx):
    class Loud(PromptSegment):
        name = "symbol"

        def render(self, ctx):
            return [("class:prompt_symbol", "!!! ")]

    renderer = PromptRenderer(full_shell, {"symbol": Loud()})
    assert renderer.render(["symbol"], ctx) == [("class:prompt_symbol", "!!! ")]


@pytest.mark.parametrize("seconds, text", [
    (0.0005, ""), (0.25, "250ms"), (1.25, "1.2s"), (75, "1m15s"), (3725, "1h2m"),
])
def test_duration_formatting(seconds, text):
    assert format_duration(seconds) == text


def test_path_shortening(full_shell, tmp_path):
    config = full_shell.config
    config.input.show_full_path = False
    config.input.path_depth = 1
    assert format_path("/a/b/c", config) == "c"
    config.input.path_depth = 2
    assert format_path("/a/b/c", config) == "b/c"
    config.input.show_full_path = True
    assert format_path("/a/b/c", config) == "/a/b/c"


def test_plugin_segments_and_key_bindings_reach_the_shell(tmp_path, isolated_config):
    from prompt_toolkit.key_binding import KeyBindings

    from zem.core.shell import Shell

    directory = tmp_path / "plugins"
    directory.mkdir()
    (directory / "decorate.py").write_text('''
from prompt_toolkit.key_binding import KeyBindings

from zem.plugin import Plugin
from zem.ui.prompt import PromptSegment


class Smiley(PromptSegment):
    name = "smiley"

    def render(self, ctx):
        return [("class:path", ":) ")]


class DecoratePlugin(Plugin):
    def prompt_segments(self):
        return {"smiley": Smiley()}

    def key_bindings(self):
        bindings = KeyBindings()

        @bindings.add("c-t")
        def _(event):
            pass

        return bindings
''')
    import sys

    sys.modules.pop("decorate", None)
    shell = Shell(commands=None, config=isolated_config, headless=True,
                  user_plugins_dir=str(directory))
    try:
        assert "smiley" in shell.prompt_renderer.segments
        ctx = PromptContext(shell=shell, cwd=str(tmp_path), exit_code=0)
        assert shell.prompt_renderer.render(["smiley"], ctx) == [("class:path", ":) ")]
        assert len(shell.plugins.key_bindings()) == 1
        assert isinstance(shell.plugins.key_bindings()[0], KeyBindings)
    finally:
        sys.modules.pop("decorate", None)
