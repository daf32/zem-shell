"""Tests for config-file bootstrap in zem.config.settings."""

import json
import subprocess
import sys
import threading

import pytest

from zem.config.settings import AppConfig
from zem.config.store import read_raw, update_raw, write_raw


def test_first_run_creates_valid_config(tmp_path):
    """Importing settings with a missing ZEM_CONFIG_PATH must create a
    valid JSON file instead of crashing on the half-written empty file.

    Runs in a subprocess because `_ensure_config_file` fires at import time
    and the module is already imported in the test process.
    """
    cfg = tmp_path / "nested" / "config.json"
    code = (
        "from zem.config.settings import AppConfig; "
        "print(AppConfig().active_theme)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={"ZEM_CONFIG_PATH": str(cfg), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "default"
    assert json.loads(cfg.read_text())["active_theme"] == "default"


# ---------------------------------------------------------------------------
# config store and the `config` builtin
# ---------------------------------------------------------------------------

def test_store_roundtrip_and_missing(tmp_path):
    path = tmp_path / "nested" / "cfg.json"
    assert read_raw(str(path)) == {}
    write_raw(str(path), {"a": 1})
    assert read_raw(str(path)) == {"a": 1}
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]


def test_store_rejects_non_object(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text("[1, 2]")
    with pytest.raises(ValueError):
        read_raw(str(path))


def test_update_raw_is_atomic_under_contention(tmp_path):
    path = str(tmp_path / "cfg.json")
    write_raw(path, {"n": 0})

    def bump(_):
        for _ in range(50):
            update_raw(path, lambda d: d.__setitem__("n", d["n"] + 1))

    threads = [threading.Thread(target=bump, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert read_raw(path)["n"] == 200


def test_config_set_validates_before_writing(full_shell, run, monkeypatch, tmp_path):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(path))
    write_raw(str(path), {"input": {"path_depth": 2}})
    code, out, err = run(full_shell, "config set input.path_depth -1")
    assert code == 1 and out == ""
    assert "input.path_depth" in err and "nothing written" in err
    assert read_raw(str(path)) == {"input": {"path_depth": 2}}  # untouched


def test_config_set_get_unset(full_shell, run, monkeypatch, tmp_path):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(path))
    assert run(full_shell, "config set input.path_depth 3")[0] == 0
    assert read_raw(str(path))["input"]["path_depth"] == 3
    assert run(full_shell, "config get input.path_depth")[1] == "3\n"
    assert run(full_shell, "config unset input.path_depth")[0] == 0
    assert "path_depth" not in read_raw(str(path)).get("input", {})
    code, _, err = run(full_shell, "config get input.path_depth")
    assert code == 1 and "not found" in err
    assert run(full_shell, "config unset nope.key")[0] == 1
    assert run(full_shell, "config set")[0] == 2
    assert run(full_shell, "config frob")[0] == 2


def test_config_set_rejects_unknown_operator_conflict(full_shell, run, monkeypatch, tmp_path):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(path))
    # Making `pipe` the same symbol as `semicolon` is rejected by
    # validate_unique_operators; the shell must not persist it.
    code, _, err = run(full_shell, "config set operators.pipe ';'")
    assert code == 1 and "operators" in err
    assert read_raw(str(path)) == {}


def test_theme_and_plugin_sync_keep_each_others_keys(full_shell, run, monkeypatch, tmp_path):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(path))
    write_raw(str(path), {"plugins": {"weather": {"default_city": "Oslo"}}})
    run(full_shell, "theme set nord")
    data = read_raw(str(path))
    assert data["active_theme"] == "nord"
    assert data["plugins"]["weather"]["default_city"] == "Oslo"
    # Plugin default sync only adds missing entries.
    full_shell._sync_plugin_configs()
    assert read_raw(str(path))["plugins"]["weather"]["default_city"] == "Oslo"


def test_format_validation_error():
    from pydantic import ValidationError

    from zem.config.settings import AppConfig, format_validation_error

    with pytest.raises(ValidationError) as info:
        AppConfig.model_validate({"input": {"path_depth": -1}})
    lines = format_validation_error(info.value)
    assert len(lines) == 1 and lines[0].startswith("input.path_depth: ")


def test_unprefixed_environment_variables_are_ignored(monkeypatch):
    # `PROMPT` is exported by some zsh setups, `INPUT` by CI scripts; neither
    # may stop the shell from starting.
    monkeypatch.setenv("PROMPT", "not json")
    monkeypatch.setenv("INPUT", "x")
    monkeypatch.setenv("HISTORY", "{}")
    assert AppConfig().input.prompt == "#"


def test_zem_prefixed_environment_variables_apply(monkeypatch):
    monkeypatch.setenv("ZEM_ACTIVE_THEME", "nord")
    assert AppConfig().active_theme == "nord"


def test_unknown_config_keys_are_reported_by_dotted_path():
    from zem.config.settings import unknown_config_keys

    data = {
        "histroy": {"max_entries": 5},
        "input": {"prompt": ">", "promt": ">"},
        "plugins": {"weather": {"default_city": "Oslo"}},
        "prompt": {"modules": {"git": {"format": "x"}}},
        "colors": "not a section",
    }
    assert unknown_config_keys(data) == ["histroy", "input.promt"]


def test_config_set_refuses_an_unknown_key(full_shell, run, monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(path))
    write_raw(str(path), {})
    code, _, err = run(full_shell, "config set nonexistent.key 1")
    assert code == 1 and "unknown key 'nonexistent.key'" in err
    assert "nonexistent" not in read_raw(str(path))
    code, _, err = run(full_shell, "config set input.promt '>'")
    assert code == 1 and "unknown key" in err
    assert run(full_shell, "config set plugins.weather.default_city Oslo")[0] == 0
    assert run(full_shell, "config set prompt.modules.git.format x")[0] == 0


def test_shell_warns_about_unknown_keys_at_startup(
    make_headless_shell, monkeypatch, tmp_path, capsys
):
    path = tmp_path / "config.json"
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(path))
    write_raw(str(path), {"histroy": {"max_entries": 5}, "input": {"promt": ">"}})
    shell = make_headless_shell()
    shell._warn_unknown_config_keys()
    err = capsys.readouterr().err
    assert "unknown key 'histroy'" in err and "unknown key 'input.promt'" in err
