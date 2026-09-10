"""pushd / popd / dirs, eval, exec."""

import os

import pytest


@pytest.fixture
def dirs(tmp_path, monkeypatch, full_shell):
    for n in ("a", "b"):
        (tmp_path / n).mkdir()
    monkeypatch.chdir(tmp_path)
    full_shell.context.set_var("PWD", str(tmp_path), export=True)
    full_shell.context.set_var("HOME", str(tmp_path / "nohome"), export=True)
    full_shell.context._dir_stack.clear()
    return tmp_path


def test_pushd_popd_roundtrip(dirs, full_shell, run):
    code, out, _ = run(full_shell, "pushd a")
    assert code == 0 and out == f"{dirs / 'a'} {dirs}\n"
    assert os.getcwd() == str(dirs / "a")
    assert run(full_shell, "dirs")[1] == f"{dirs / 'a'} {dirs}\n"
    code, out, _ = run(full_shell, "popd")
    assert code == 0 and out == f"{dirs}\n"
    assert os.getcwd() == str(dirs)


def test_pushd_no_args_swaps(dirs, full_shell, run):
    run(full_shell, "pushd a")
    assert run(full_shell, "pushd")[1] == f"{dirs} {dirs / 'a'}\n"
    assert os.getcwd() == str(dirs)


def test_pushd_popd_errors(dirs, full_shell, run):
    code, _, err = run(full_shell, "popd")
    assert code == 1 and "stack empty" in err
    code, _, err = run(full_shell, "pushd")
    assert code == 1 and "no other directory" in err
    code, _, err = run(full_shell, "pushd nope")
    assert code == 1 and "No such file" in err
    assert full_shell.context._dir_stack == []      # nothing pushed on failure
    assert run(full_shell, "pushd a b")[0] == 2
    assert run(full_shell, "popd x")[0] == 2


def test_dirs_home_abbreviation_and_clear(dirs, full_shell, run):
    full_shell.context.set_var("HOME", str(dirs), export=True)
    run(full_shell, "pushd a")
    assert run(full_shell, "dirs")[1] == "~/a ~\n"
    assert run(full_shell, "dirs -c")[0] == 0
    assert full_shell.context._dir_stack == []
    assert run(full_shell, "dirs -x")[0] == 2


def test_eval_joins_and_runs(full_shell, run):
    run(full_shell, "set CMD 'echo from eval'")
    assert run(full_shell, "eval $CMD") == (0, "from eval\n", "")
    assert run(full_shell, "eval echo a '|' cat")[1] == "a\n"
    assert run(full_shell, "eval false")[0] == 1
    assert run(full_shell, "eval")[0] == 0


def test_exec_missing_and_no_args(full_shell, run):
    assert run(full_shell, "exec")[0] == 0
    code, _, err = run(full_shell, "exec nope-cmd-xyz")
    assert code == 127 and "not found" in err


def test_exec_replaces_process(tmp_path):
    """Run a headless shell in a subprocess and `exec /bin/echo`; the
    subprocess's stdout must be echo's output and nothing after it."""
    import subprocess
    import sys

    code = f"""
import sys
sys.path.insert(0, {str(tmp_path)!r})
from zem.config.settings import AppConfig
from zem.core.shell import Shell
cfg = AppConfig(history={{"file": {str(tmp_path / "h")!r}, "load_on_start": False,
                          "save_on_exit": False}},
                rc={{"auto_create": False, "file": {str(tmp_path / "rc")!r}}},
                venv={{"auto": False}})
sh = Shell(config=cfg, headless=True, user_plugins_dir=None)
sh._execute_line("exec /bin/echo replaced")
print("NOT REACHED")
"""
    env = {**os.environ, "ZEM_CONFIG_PATH": str(tmp_path / "cfg.json")}
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert result.stdout == "replaced\n", result.stderr
