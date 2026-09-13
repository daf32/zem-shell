def test_theme_shows_current(full_shell, run):
    code, out, _ = run(full_shell, "theme")
    assert code == 0 and out.startswith("Current theme: default")


def test_theme_list_is_plain_in_capture(full_shell, run):
    code, out, _ = run(full_shell, "theme list")
    assert code == 0
    assert "nord" in out.lower() and "\x1b[" not in out


def test_theme_set_applies_live_config(full_shell, run):
    before = full_shell.config.colors.command
    assert run(full_shell, "theme set nord")[0] == 0
    assert full_shell.config.active_theme == "nord"
    assert full_shell.config.colors.command != before
    assert run(full_shell, "theme")[1].startswith("Current theme: nord")


def test_theme_set_unknown_fails(full_shell, run):
    code, _, err = run(full_shell, "theme set nope")
    assert code == 1 and "not found" in err


def test_theme_preview_unknown_and_usage(full_shell, run):
    assert run(full_shell, "theme preview nope")[0] == 1
    assert run(full_shell, "theme set")[0] == 2
    assert run(full_shell, "theme bogus")[0] == 2


def test_theme_variants(full_shell, run):
    code, out, _ = run(full_shell, "theme variants solarized")
    assert code == 0 and "solarized_dark" in out
    assert run(full_shell, "theme variants nope")[0] == 1


# -- import / install / export -----------------------------------------------

import json  # noqa: E402

import pytest  # noqa: E402

from zem.utils.themes import ThemeError, ThemeManager, theme_name  # noqa: E402

VALID_COLORS = {key: "#123456" for key in ThemeManager.REQUIRED_COLORS}


@pytest.fixture
def manager(full_shell, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    return ThemeManager(full_shell.config, full_shell.plugins.theme_dirs())


def _theme_file(tmp_path, name, **extra):
    path = tmp_path / "src.json"
    path.write_text(json.dumps({"name": name, "colors": VALID_COLORS, **extra}))
    return path


def test_theme_name_is_normalised_and_checked():
    assert theme_name("My Theme") == "my_theme"
    for bad in ("../../pwned", "a/b", "", ".hidden", "x" * 65, "name with\ttab"):
        with pytest.raises(ThemeError):
            theme_name(bad)


def test_import_writes_under_the_themes_directory(manager, tmp_path):
    src = _theme_file(tmp_path, "Ocean Blue")
    assert manager.import_theme(str(src)) == "ocean_blue"
    assert (tmp_path / ".zem" / "themes" / "ocean_blue.json").exists()
    assert "ocean_blue" in manager.list_themes()


def test_import_refuses_a_name_that_leaves_the_directory(manager, tmp_path):
    src = _theme_file(tmp_path, "../../pwned")
    with pytest.raises(ThemeError, match="not a valid theme name"):
        manager.import_theme(str(src))
    assert not (tmp_path / "pwned.json").exists()
    assert not list((tmp_path / ".zem").rglob("*.json")) if (tmp_path / ".zem").exists() else True


def test_import_refuses_an_invalid_theme_before_writing(manager, tmp_path):
    src = tmp_path / "bad.json"
    src.write_text(json.dumps({"name": "bad", "colors": {"command": "red"}}))
    with pytest.raises(ThemeError, match="invalid theme"):
        manager.import_theme(str(src))
    assert not (tmp_path / ".zem" / "themes" / "bad.json").exists()
    src.write_text("[1, 2]")
    with pytest.raises(ThemeError, match="JSON object"):
        manager.import_theme(str(src))
    src.write_text("{not json")
    with pytest.raises(ThemeError, match="not valid JSON"):
        manager.import_theme(str(src))


def test_import_falls_back_to_the_file_name(manager, tmp_path):
    src = tmp_path / "Night Sky.json"
    src.write_text(json.dumps({"colors": VALID_COLORS}))
    assert manager.import_theme(str(src)) == "night_sky"


@pytest.mark.parametrize("url", ["http://example.test/t.json", "file:///tmp/t.json"])
def test_install_refuses_unsafe_urls_without_fetching(manager, url, monkeypatch):
    import urllib.request

    def boom(*a, **k):
        raise AssertionError("must not fetch")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    with pytest.raises(ThemeError, match="only https"):
        manager.install_theme(url)


def test_install_stores_a_valid_download(manager, tmp_path, monkeypatch):
    import urllib.request

    body = json.dumps({"name": "Remote", "colors": VALID_COLORS}).encode()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n=-1):
            return body

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Response())
    assert manager.install_theme("https://example.test/remote.json") == "remote"
    assert (tmp_path / ".zem" / "themes" / "remote.json").exists()


def test_theme_command_reports_the_reason(full_shell, run, tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    src = _theme_file(tmp_path, "../../pwned")
    code, _, err = run(full_shell, f"theme import {src}")
    assert code == 1 and "not a valid theme name" in err
    code, _, err = run(full_shell, "theme install http://example.test/t.json")
    assert code == 1 and "only https" in err
    code, _, err = run(full_shell, "theme export ../escape")
    assert code == 1 and "not a valid theme name" in err
