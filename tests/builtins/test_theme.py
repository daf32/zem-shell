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
