"""The prompt: the format language, the modules, and the renderer."""

import pytest

from zem.ui.prompt import PromptContext, PromptModule, PromptRenderer, format_duration
from zem.ui.prompt import format as fmt
from zem.ui.prompt.modules import format_path

# -- the format language ---------------------------------------------------

def _render(text, values, style_map=None):
    return fmt.render(fmt.parse(text), lambda name: values.get(name),
                      style_map or (lambda s: s))


def test_plain_text():
    assert _render("hello", {}) == [("", "hello")]


def test_variable_substitution():
    assert _render("$a-$b", {"a": "1", "b": "2"}) == [
        ("", "1"), ("", "-"), ("", "2"),
    ]


def test_braced_variable():
    assert _render("${name}s", {"name": "cat"}) == [("", "cat"), ("", "s")]


def test_missing_variable_renders_nothing():
    assert _render("a${nope}b", {}) == [("", "a"), ("", "b")]


def test_style_group():
    assert _render("[$a](bold red)", {"a": "x"}) == [("bold red", "x")]


def test_nested_style_groups():
    fragments = _render("[a[$b](red)c](green)", {"b": "B"})
    assert fragments == [("green", "a"), ("red", "B"), ("green", "c")]


def test_conditional_group_renders_when_filled():
    assert _render("x( on $b)", {"b": "main"}) == [
        ("", "x"), ("", " on "), ("", "main"),
    ]


def test_conditional_group_vanishes_with_its_punctuation():
    # The whole point: " on (branch)" must disappear outside a repository,
    # rather than leaving a dangling " on ".
    assert _render("x( on $b)", {}) == [("", "x")]


def test_conditional_group_without_variables_is_literal():
    assert _render("(just text)", {}) == [("", "just text")]


@pytest.mark.parametrize("text, expected", [
    (r"\$notavar", "$notavar"),
    (r"\[literal\]", "[literal]"),
    (r"\(parens\)", "(parens)"),
])
def test_escapes(text, expected):
    assert _render(text, {}) == [("", expected)]


@pytest.mark.parametrize("text", ["[unclosed", "[a](b", "${unclosed", "$", "(open", "a\\"])
def test_malformed_formats_are_rejected(text):
    with pytest.raises(fmt.FormatError):
        fmt.parse(text)


# -- the renderer ----------------------------------------------------------

@pytest.fixture
def ctx(full_shell, tmp_path):
    full_shell.config.input.show_venv_info = False
    full_shell.config.input.show_git_info = False
    return PromptContext(shell=full_shell, cwd=str(tmp_path), exit_code=0)


@pytest.fixture
def renderer(full_shell):
    return PromptRenderer(full_shell)


def test_default_format(renderer, ctx):
    fragments = renderer.render(ctx.shell.config.prompt.format, ctx)
    assert [style for style, _ in fragments] == [
        "class:exit_code_ok", "class:exit_code_ok", "class:path",
        "", "class:prompt_symbol", "",
    ]


def test_exit_code_colour_follows_the_status(renderer, ctx):
    assert renderer.render("$exit_code", ctx)[0][0] == "class:exit_code_ok"
    ctx.exit_code = 1
    assert renderer.render("$exit_code", ctx)[0][0] == "class:exit_code_err"


def test_modules_can_be_reordered_and_have_text_between_them(renderer, ctx):
    assert renderer.render("$path :: $exit_code", ctx, colored=False).endswith(":: 0 ")


def test_a_module_with_nothing_to_say_disappears(renderer, ctx):
    ctx.shell.config.input.show_exit_code = False
    assert renderer.render("$exit_code", ctx) == []


def test_module_format_can_be_overridden(renderer, ctx):
    ctx.shell.config.prompt.modules = {"path": {"format": "<[$path](bold blue)>"}}
    fragments = renderer.render("$path", ctx)
    assert fragments[0] == ("", "<")
    assert fragments[1][0] == "bold blue"


def test_module_style_can_be_overridden(renderer, ctx):
    ctx.shell.config.prompt.modules = {"path": {"style": "fg:#ff8800"}}
    assert renderer.render("$path", ctx)[0][0] == "fg:#ff8800"


def test_a_module_can_be_disabled(renderer, ctx):
    ctx.shell.config.prompt.modules = {"path": {"disabled": True}}
    assert renderer.render("$path", ctx) == []


def test_theme_colour_keys_become_style_classes(renderer, ctx):
    assert renderer.render("[x](path)", ctx) == [("class:path", "x")]
    assert renderer.render("[x](git_branch)", ctx) == [("class:git_branch", "x")]


def test_literal_styles_pass_through(renderer, ctx):
    assert renderer.render("[x](bold green)", ctx) == [("bold green", "x")]


def test_plain_text_mode_is_the_same_content(renderer, ctx):
    coloured = renderer.render("$exit_code$path", ctx)
    plain = renderer.render("$exit_code$path", ctx, colored=False)
    assert plain == "".join(text for _style, text in coloured)


def test_an_unknown_module_is_skipped(renderer, ctx):
    assert renderer.render("$exit_code$nosuchmodule", ctx, colored=False) == "0 "


def test_a_broken_format_does_not_lose_the_prompt(renderer, ctx):
    assert renderer.render("[unclosed", ctx) == []
    assert renderer.render("[unclosed", ctx, colored=False) == ""


def test_a_module_that_raises_is_contained(renderer, ctx):
    class Exploding(PromptModule):
        name = "boom"
        default_format = "$x"

        def variables(self, ctx):
            raise RuntimeError("no prompt for you")

    renderer.modules["boom"] = Exploding()
    assert renderer.render("$boom$exit_code", ctx, colored=False) == "0 "


def test_venv_and_git_respect_their_settings(renderer, ctx, monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/some-venv")
    ctx.shell.config.input.show_venv_info = False
    assert renderer.render("$venv", ctx) == []
    ctx.shell.config.input.show_venv_info = True
    assert renderer.render("$venv", ctx, colored=False) == "[some-venv] "


def test_duration_below_the_threshold_is_not_shown(renderer, ctx):
    ctx.duration = 0.01
    assert renderer.render("$duration", ctx) == []
    ctx.duration = 1.25
    assert renderer.render("$duration", ctx, colored=False) == "⏱ 1.2s "


@pytest.mark.parametrize("seconds, text", [
    (0.0005, ""), (0.25, "250ms"), (1.25, "1.2s"), (75, "1m15s"), (3725, "1h2m"),
])
def test_duration_formatting(seconds, text):
    assert format_duration(seconds) == text


def test_path_shortening(full_shell):
    config = full_shell.config
    config.input.show_full_path = False
    config.input.path_depth = 1
    assert format_path("/a/b/c", config) == "c"
    config.input.path_depth = 2
    assert format_path("/a/b/c", config) == "b/c"
    config.input.show_full_path = True
    assert format_path("/a/b/c", config) == "/a/b/c"


def test_a_plugin_module_can_replace_a_builtin(full_shell, ctx):
    class Loud(PromptModule):
        name = "symbol"
        default_format = "[$symbol]($style)"
        default_style = "error"

        def variables(self, ctx):
            return {"symbol": "!!!"}

    renderer = PromptRenderer(full_shell, {"symbol": Loud()})
    assert renderer.render("$symbol", ctx) == [("class:error", "!!!")]


def test_plugin_modules_and_key_bindings_reach_the_shell(tmp_path, isolated_config):
    from prompt_toolkit.key_binding import KeyBindings

    from zem.core.shell import Shell

    directory = tmp_path / "plugins"
    directory.mkdir()
    (directory / "decorate.py").write_text('''
from prompt_toolkit.key_binding import KeyBindings

from zem.plugin import Plugin
from zem.ui.prompt import PromptModule


class Smiley(PromptModule):
    name = "smiley"
    default_format = "[$face]($style)"
    default_style = "path"

    def variables(self, ctx):
        return {"face": ":)"}


class DecoratePlugin(Plugin):
    def prompt_modules(self):
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
        assert "smiley" in shell.prompt_renderer.modules
        ctx = PromptContext(shell=shell, cwd=str(tmp_path), exit_code=0)
        assert shell.prompt_renderer.render("$smiley", ctx) == [("class:path", ":)")]
        assert len(shell.plugins.key_bindings()) == 1
        assert isinstance(shell.plugins.key_bindings()[0], KeyBindings)
    finally:
        sys.modules.pop("decorate", None)
