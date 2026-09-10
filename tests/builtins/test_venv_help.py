import os
import subprocess
import sys


def _make_venv(path):
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(path)], check=True)


def test_venv_status_activate_deactivate(tmp_path, full_shell, run, monkeypatch):
    for n in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT"):
        monkeypatch.delenv(n, raising=False)
    full_shell.context.unset_var("VIRTUAL_ENV")
    full_shell.context.active_venv = None
    venv = tmp_path / "myenv"
    _make_venv(venv)

    assert run(full_shell, "venv")[1] == "✗ No venv active\n"
    code, out, _ = run(full_shell, f"venv activate {venv}")
    assert code == 0 and str(venv) in out
    env = full_shell.context.child_env()
    assert env["VIRTUAL_ENV"] == str(venv)
    assert env["PATH"].startswith(str(venv / "bin") + os.pathsep)

    assert run(full_shell, "venv deactivate")[0] == 0
    assert "VIRTUAL_ENV" not in full_shell.context.child_env()
    assert run(full_shell, "venv deactivate")[0] == 1


def test_venv_activate_bad_path_and_nothing_found(tmp_path, full_shell, run, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run(full_shell, f"venv activate {tmp_path / 'nope'}")[0] == 1
    assert run(full_shell, "venv activate")[0] == 1
    assert run(full_shell, "venv frobnicate")[0] == 2


def test_help_lists_and_details(full_shell, run):
    code, out, _ = run(full_shell, "help")
    assert code == 0 and "cd" in out and "\x1b[" not in out
    code, out, _ = run(full_shell, "help cd")
    assert code == 0 and "Usage: cd" in out


def test_help_unknown_and_alias(full_shell, run):
    code, out, err = run(full_shell, "help nope")
    assert (code, out) == (1, "") and "not found" in err
    run(full_shell, "alias ll='ls -la'")
    assert run(full_shell, "help ll")[1] == "'ll' is an alias for: ls -la\n"


def test_logo_returns_zero(full_shell, run):
    from zem import __version__
    assert run(full_shell, "logo")[0] == 0
    assert __version__ in run(full_shell, "logo --version")[1]
