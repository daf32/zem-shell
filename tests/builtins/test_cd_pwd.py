"""cd / pwd."""

import os

import pytest


@pytest.fixture
def start(tmp_path, monkeypatch, full_shell):
    """Run each test from a fresh tmp dir with HOME pointing at tmp_path/home."""
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "a" / "b").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    full_shell.context.set_var("HOME", str(home), export=True)
    full_shell.context.unset_var("OLDPWD")
    full_shell.context.set_var("PWD", str(tmp_path), export=True)
    return tmp_path


def test_cd_relative_and_pwd(start, full_shell, run):
    assert run(full_shell, "cd a/b")[0] == 0
    assert os.getcwd() == str(start / "a" / "b")
    assert run(full_shell, "pwd") == (0, f"{start / 'a' / 'b'}\n", "")


def test_cd_updates_exported_pwd_and_oldpwd(start, full_shell, run):
    run(full_shell, "cd a")
    env = full_shell.context.child_env()
    assert env["PWD"] == str(start / "a")
    assert env["OLDPWD"] == str(start)


def test_cd_no_args_goes_home(start, full_shell, run):
    run(full_shell, "cd a")
    assert run(full_shell, "cd")[0] == 0
    assert os.getcwd() == str(start / "home")


def test_cd_home_unset_errors(start, full_shell, run):
    full_shell.context.unset_var("HOME")
    code, _, err = run(full_shell, "cd")
    assert code == 1 and "HOME not set" in err


def test_cd_dash_prints_and_toggles(start, full_shell, run):
    run(full_shell, "cd a")
    assert run(full_shell, "cd -") == (0, f"{start}\n", "")
    assert run(full_shell, "cd -") == (0, f"{start / 'a'}\n", "")


def test_cd_dash_without_oldpwd_errors(start, full_shell, run):
    code, _, err = run(full_shell, "cd -")
    assert code == 1 and "OLDPWD not set" in err


def test_cd_missing_and_not_a_directory(start, full_shell, run):
    (start / "file").write_text("")
    code, _, err = run(full_shell, "cd nope")
    assert code == 1 and "No such file or directory" in err
    code, _, err = run(full_shell, "cd file")
    assert code == 1 and "Not a directory" in err


def test_cd_too_many_arguments(start, full_shell, run):
    assert run(full_shell, "cd a b")[0] == 2


def test_cd_tilde_expands(start, full_shell, run, monkeypatch):
    monkeypatch.setenv("HOME", str(start / "home"))  # expanduser reads os.environ
    assert run(full_shell, "cd ~")[0] == 0
    assert os.getcwd() == str(start / "home")


def test_pwd_logical_keeps_symlink_physical_resolves(start, full_shell, run):
    link = start / "link"
    link.symlink_to(start / "a")
    run(full_shell, "cd link")
    assert run(full_shell, "pwd")[1] == f"{link}\n"
    assert run(full_shell, "pwd -P")[1] == f"{(start / 'a').resolve()}\n"
    assert run(full_shell, "pwd -x")[0] == 2
