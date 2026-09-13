"""The git module of the prompt: parsing, one isolated call, real repos."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from zem.utils import git as gitmod
from zem.utils.git import GitStatus, get_git_info, git_status, parse_status

CLEAN = """\
# branch.oid 1111111111111111111111111111111111111111
# branch.head main
# branch.upstream origin/main
# branch.ab +0 -0
"""


# -- the parser (no git involved) --------------------------------------------

def test_clean_branch():
    assert parse_status(CLEAN) == GitStatus(branch="main", ahead=0, behind=0, dirty=False)
    assert parse_status(CLEAN).symbols == ""


@pytest.mark.parametrize("entry", [
    "1 .M N... 100644 100644 100644 1111111 1111111 file.txt",
    "2 R. N... 100644 100644 100644 1111111 1111111 R100 new\told",
    "u UU N... 100644 100644 100644 100644 1111111 1111111 1111111 conflict.txt",
    "? untracked.txt",
])
def test_any_entry_line_means_dirty(entry):
    status = parse_status(CLEAN + entry + "\n")
    assert status.dirty is True
    assert status.symbols == "*"


def test_ahead_and_behind_are_not_swapped():
    ahead = parse_status(CLEAN.replace("+0 -0", "+3 -0"))
    assert (ahead.ahead, ahead.behind, ahead.symbols) == (3, 0, "+")
    behind = parse_status(CLEAN.replace("+0 -0", "+0 -2"))
    assert (behind.ahead, behind.behind, behind.symbols) == (0, 2, "-")
    both = parse_status(CLEAN.replace("+0 -0", "+1 -1") + "? x\n")
    assert both.symbols == "*+-"


def test_detached_head_shows_the_commit():
    text = CLEAN.replace("# branch.head main", "# branch.head (detached)")
    assert parse_status(text).branch == "1111111"


def test_repository_without_commits():
    text = "# branch.oid (initial)\n# branch.head main\n"
    assert parse_status(text) == GitStatus(branch="main")


def test_detached_without_a_commit_is_named_not_blank():
    text = "# branch.oid (initial)\n# branch.head (detached)\n"
    assert parse_status(text).branch == "detached"


def test_output_without_a_branch_header_is_not_a_status():
    assert parse_status("") is None
    assert parse_status("?? old-porcelain.txt\n") is None


def test_headers_are_read_even_when_the_tree_is_dirty():
    # Entries follow the headers, so the early exit must not lose `branch.ab`.
    text = CLEAN.replace("+0 -0", "+2 -0") + "".join(f"? f{n}\n" for n in range(500))
    status = parse_status(text)
    assert (status.branch, status.ahead, status.dirty) == ("main", 2, True)


# -- how the command is run ---------------------------------------------------

def test_one_call_isolated_from_the_terminal_and_the_index(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, CLEAN, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert get_git_info("/somewhere") == ("main", "")

    (argv, kwargs), = calls
    assert argv == ["git", "status", "--porcelain=v2", "--branch"]
    assert kwargs["cwd"] == "/somewhere"
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["start_new_session"] is True
    assert kwargs["timeout"] == gitmod.DEFAULT_TIMEOUT_MS / 1000
    assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
    assert kwargs["env"]["LC_ALL"] == "C"
    assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_the_timeout_can_be_shortened(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, CLEAN, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    get_git_info("/somewhere", timeout_ms=50)
    assert seen["timeout"] == 0.05


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired(cmd="git", timeout=1),
    FileNotFoundError("git"),
    OSError("gone"),
])
def test_a_failing_git_means_no_repository(monkeypatch, failure):
    def fake_run(*a, **k):
        raise failure

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert get_git_info("/somewhere") is None


def test_a_nonzero_exit_means_no_repository(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(argv, 128, "", "fatal: not a repository"),
    )
    assert get_git_info("/somewhere") is None


# -- against a real repository -------------------------------------------------

git_required = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

GIT_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": "/nonexistent",
    # The developer's own config must not decide what these tests see:
    # a default branch name, a signing key, hooks, fsmonitor.
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Zem Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Zem Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def _git(repo, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), env=GIT_ENV,
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        pytest.skip(f"git {' '.join(args)} failed here: {proc.stderr.strip()}")
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A repository on `main` with one commit."""
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-b", "main")
    (path / "file.txt").write_text("one\n")
    _git(path, "add", "file.txt")
    _git(path, "commit", "-m", "first")
    return path


@git_required
def test_outside_a_repository(tmp_path):
    assert get_git_info(str(tmp_path)) is None


@git_required
def test_clean_repository(repo):
    assert get_git_info(str(repo)) == ("main", "")


@git_required
def test_modified_staged_and_untracked_all_count_as_dirty(repo):
    (repo / "file.txt").write_text("two\n")
    assert get_git_info(str(repo)) == ("main", "*")
    _git(repo, "add", "file.txt")
    assert get_git_info(str(repo)) == ("main", "*")
    _git(repo, "commit", "-m", "second")
    assert get_git_info(str(repo)) == ("main", "")
    (repo / "new.txt").write_text("x\n")
    assert get_git_info(str(repo)) == ("main", "*")


@git_required
def test_subdirectory_sees_the_same_repository(repo):
    (repo / "sub").mkdir()
    assert get_git_info(str(repo / "sub")) == ("main", "")


@git_required
def test_detached_head_shows_a_short_commit(repo):
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "--detach", head)
    branch, symbols = get_git_info(str(repo))
    assert branch == head[:7] and symbols == ""


@git_required
def test_ahead_and_behind_an_upstream(tmp_path, repo):
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "--quiet", str(repo), str(clone))
    assert get_git_info(str(clone)) == ("main", "")

    (clone / "local.txt").write_text("x\n")
    _git(clone, "add", "local.txt")
    _git(clone, "commit", "-m", "local")
    assert get_git_info(str(clone)) == ("main", "+"), "a local commit means ahead"

    _git(clone, "reset", "--hard", "origin/main")
    (repo / "file.txt").write_text("upstream\n")
    _git(repo, "commit", "-am", "upstream")
    _git(clone, "fetch", "--quiet", "origin")
    assert get_git_info(str(clone)) == ("main", "-"), "an upstream commit means behind"


@git_required
def test_a_repository_without_commits(tmp_path):
    path = tmp_path / "empty"
    path.mkdir()
    _git(path, "init", "-b", "main")
    assert get_git_info(str(path)) == ("main", "")


@git_required
def test_git_status_returns_the_parsed_object(repo):
    status = git_status(str(repo))
    assert status.branch == "main" and status.dirty is False


# -- the prompt module ----------------------------------------------------------

def test_module_reports_branch_and_status(full_shell, monkeypatch):
    from zem.ui.prompt import PromptContext
    from zem.ui.prompt.modules import GitModule

    monkeypatch.setattr("zem.utils.git.get_git_info", lambda cwd, timeout_ms=None: ("main", "*"))
    ctx = PromptContext(shell=full_shell, cwd="/x", exit_code=0)
    assert GitModule().variables(ctx) == {"branch": "main", "status": "*"}

    full_shell.config.input.show_git_info = False
    assert GitModule().variables(ctx) is None


def test_module_passes_its_configured_timeout(full_shell, monkeypatch):
    from zem.ui.prompt import PromptContext
    from zem.ui.prompt.modules import GitModule

    seen = {}

    def fake_info(cwd, timeout_ms=None):
        seen["timeout_ms"] = timeout_ms
        return ("a-very-long-branch-name-indeed", "")

    monkeypatch.setattr("zem.utils.git.get_git_info", fake_info)
    full_shell.config.prompt.modules = {"git": {"timeout_ms": 250, "max_length": 10}}
    ctx = PromptContext(shell=full_shell, cwd="/x", exit_code=0)

    assert GitModule().variables(ctx)["branch"] == "a-very-lo…"
    assert seen["timeout_ms"] == 250
