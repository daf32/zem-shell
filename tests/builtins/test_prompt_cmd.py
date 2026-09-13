"""The `prompt` command: presets, previews and the wizard."""

import json

import pytest

from zem.config.settings import get_config_path
from zem.config.store import read_raw
from zem.ui.prompt.presets import load_presets


@pytest.fixture
def tty(monkeypatch):
    """Pretend there is a terminal, and feed the wizard its answers."""
    def _install(answers):
        queue = list(answers)

        class FakeStdin:
            def isatty(self):
                return True

            def readline(self):
                return (queue.pop(0) if queue else "") + "\n"

        monkeypatch.setattr("sys.stdin", FakeStdin())
        return queue

    return _install


def test_every_bundled_preset_loads_and_renders(full_shell):
    from zem.ui.prompt import PromptContext

    presets = load_presets(user_dir="/nonexistent")
    assert {"classic", "minimal", "pure", "powerline", "two_line", "verbose"} <= set(presets)

    ctx = PromptContext(shell=full_shell, cwd="/tmp", exit_code=0, duration=1.2)
    for preset in presets.values():
        full_shell.config.prompt.modules = preset.modules
        full_shell.prompt_renderer._parsed.clear()
        rendered = full_shell.prompt_renderer.render(
            preset.format, ctx, colored=False, sample=True)
        assert rendered.strip(), f"{preset.name} rendered nothing"


def test_show(full_shell, run):
    code, out, _ = run(full_shell, "prompt")
    assert code == 0
    assert "format" in out and "looks like" in out


def test_list_previews_each_preset(full_shell, run):
    code, out, _ = run(full_shell, "prompt list")
    assert code == 0
    for name in ("classic", "minimal", "pure"):
        assert name in out
    assert "~ project" in out  # the sample path, so a preview was drawn


def test_preview(full_shell, run):
    code, out, _ = run(full_shell, "prompt preview minimal")
    assert code == 0 and "~ project" in out


def test_preview_unknown(full_shell, run):
    code, _, err = run(full_shell, "prompt preview nope")
    assert code == 1 and "no preset" in err


def test_set_writes_the_config_and_applies_live(full_shell, run):
    code, out, _ = run(full_shell, "prompt set minimal")
    assert code == 0 and "minimal" in out

    written = read_raw(get_config_path())["prompt"]
    assert written["format"] == load_presets()["minimal"].format
    # And the running shell already uses it.
    assert full_shell.config.prompt.format == written["format"]


def test_set_unknown_preset(full_shell, run):
    code, _, err = run(full_shell, "prompt set nope")
    assert code == 1 and "no preset named" in err


def test_reset_restores_the_default(full_shell, run):
    from zem.config.settings import PromptSettings

    run(full_shell, "prompt set minimal")
    code, _, _ = run(full_shell, "prompt reset")
    assert code == 0
    assert full_shell.config.prompt.format == PromptSettings().format


def test_configure_needs_a_terminal(full_shell, run, monkeypatch):
    monkeypatch.setattr("sys.stdin", type("T", (), {"isatty": lambda self: False})())
    code, _, err = run(full_shell, "prompt configure")
    assert code == 1 and "needs a terminal" in err


def test_configure_applies_the_chosen_preset(full_shell, run, tty):
    names = sorted(load_presets())
    choice = names.index("minimal") + 1
    # preset, then the prompt character, then "keep it?"
    tty([str(choice), "", "y"])
    code, out, _ = run(full_shell, "prompt configure")
    assert code == 0, out
    assert full_shell.config.prompt.format == load_presets()["minimal"].format


def test_configure_can_be_cancelled(full_shell, run, tty):
    before = full_shell.config.prompt.format
    tty(["q"])
    code, out, _ = run(full_shell, "prompt configure")
    assert code == 1 and "Cancelled" in out
    assert full_shell.config.prompt.format == before


def test_configure_rejects_a_nonsense_choice(full_shell, run, tty):
    tty(["42"])
    code, _, err = run(full_shell, "prompt configure")
    assert code == 2 and "not one of the options" in err


def test_configure_saying_no_disables_a_module(full_shell, run, tty):
    names = sorted(load_presets())
    choice = names.index("classic") + 1
    # classic mentions git, venv, duration and time: answer no to git,
    # yes to the rest, keep the symbol, then keep the result.
    tty([str(choice), "n", "y", "y", "y", "", "y"])
    code, out, _ = run(full_shell, "prompt configure")
    assert code == 0, out
    assert full_shell.config.prompt.modules["git"]["disabled"] is True


def test_configure_can_change_the_prompt_character(full_shell, run, tty):
    names = sorted(load_presets())
    choice = names.index("minimal") + 1
    tty([str(choice), "λ", "y"])
    code, _, _ = run(full_shell, "prompt configure")
    assert code == 0
    assert full_shell.config.input.prompt == "λ"
    assert read_raw(get_config_path())["input"]["prompt"] == "λ"


def test_user_presets_override_bundled(tmp_path):
    directory = tmp_path / "prompts"
    directory.mkdir()
    (directory / "minimal.json").write_text(json.dumps({
        "name": "minimal", "description": "mine", "format": "$symbol",
    }))
    presets = load_presets(user_dir=str(directory))
    assert presets["minimal"].description == "mine"
    assert presets["minimal"].origin == "user"


def test_a_broken_preset_is_skipped(tmp_path):
    directory = tmp_path / "prompts"
    directory.mkdir()
    (directory / "broken.json").write_text("{not json")
    (directory / "fine.json").write_text(json.dumps({"name": "fine", "format": "$symbol"}))
    presets = load_presets(user_dir=str(directory))
    assert "fine" in presets and "broken" not in presets


def test_unknown_subcommand(full_shell, run):
    code, _, err = run(full_shell, "prompt frobnicate")
    assert code == 2 and "unknown subcommand" in err
