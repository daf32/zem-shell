"""The shell in a real pseudo-terminal.

Everything the headless fixtures cannot reach lives here: prompt_toolkit,
the signal handlers, job control against a tty, termios restore. Each
test drives the `zem` console script through pexpect with an isolated
HOME, so nothing touches the developer's rc file, history or config.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import termios
import time

import pytest

pexpect = pytest.importorskip("pexpect")

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith(("linux", "darwin")), reason="needs a Unix pty"
)

PROMPT_SYMBOL = "ZEM>"
#: The prompt as prompt_toolkit renders it: the symbol, then a style reset.
PROMPT = re.compile(r"ZEM>\x1b\[0m")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[=>]")


def _zem_executable() -> str:
    exe = shutil.which("zem") or os.path.join(os.path.dirname(sys.executable), "zem")
    if not os.path.exists(exe):
        pytest.skip("the zem console script is not installed in this environment")
    return exe


@pytest.fixture
def home(tmp_path):
    """An isolated HOME with a config whose prompt is easy to match."""
    home = tmp_path / "home"
    (home / ".config" / "zem").mkdir(parents=True)
    config = {
        "input": {"prompt": PROMPT_SYMBOL, "rprompt": False, "show_git_info": False,
                  "show_venv_info": False},
        "prompt": {"format": "$symbol"},
        "rc": {"auto_create": False},
        "venv": {"auto": False},
    }
    (home / ".config" / "zem" / "config.json").write_text(json.dumps(config))
    return home


class Session:
    def __init__(self, exe: str, home, env_extra: dict | None = None):
        env = {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "ZEM_CONFIG_PATH": str(home / ".config" / "zem" / "config.json"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TERM": "xterm-256color",
            "LANG": "en_US.UTF-8",
            # No cursor-position round trip: a pty with nobody answering
            # would make every prompt wait a second for the reply.
            "PROMPT_TOOLKIT_NO_CPR": "1",
        }
        env.update(env_extra or {})
        self.child = pexpect.spawn(exe, env=env, cwd=str(home), dimensions=(30, 120),
                                   encoding="utf-8", timeout=10)

    # prompt_toolkit redraws the prompt line when a line is accepted, so the
    # prompt string appears more than once per command: wait until it has
    # been seen and the pty is quiet.
    def wait_prompt(self, timeout: float = 10, quiet: float = 0.4) -> str:
        deadline = time.time() + timeout
        seen = False
        chunks: list[str] = []
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise AssertionError("no prompt within %ss: %r" % (timeout, "".join(chunks)[-300:]))
            i = self.child.expect([PROMPT, pexpect.TIMEOUT],
                                  timeout=quiet if seen else remaining)
            chunks.append(ANSI.sub("", self.child.before).replace("\r", ""))
            if i == 0:
                seen = True
                chunks.append(PROMPT_SYMBOL)
            elif seen:
                return "".join(chunks)

    def run(self, line: str, **kw) -> str:
        self.child.sendline(line)
        return self.wait_prompt(**kw)

    def output_of(self, line: str, **kw) -> str:
        """What a command printed, without the echoed line and the prompt."""
        out = self.run(line, **kw)
        body = out.split(line, 1)[-1]
        return body.rsplit(PROMPT_SYMBOL, 1)[0].strip("\n ")

    def exit(self):
        self.child.sendline("exit")
        self.child.expect(pexpect.EOF, timeout=10)
        return ANSI.sub("", self.child.before)

    def close(self):
        self.child.close(force=True)


@pytest.fixture
def session(home):
    s = Session(_zem_executable(), home)
    s.wait_prompt()
    yield s
    s.close()


# -- startup and basics -------------------------------------------------------

def test_prompt_runs_a_command(session):
    assert session.output_of("echo hello") == "hello"
    assert session.output_of("echo $?") == "0"


def test_parent_environment_names_do_not_break_startup(home):
    s = Session(_zem_executable(), home, {"PROMPT": "not json", "INPUT": "x"})
    try:
        s.wait_prompt()
        assert s.output_of("echo started") == "started"
    finally:
        s.close()


def test_broken_config_is_reported_not_crashed(home):
    path = home / ".config" / "zem" / "config.json"
    data = json.loads(path.read_text())
    data["history"] = {"max_entries": -1}
    path.write_text(json.dumps(data))
    s = Session(_zem_executable(), home)
    try:
        s.child.expect(pexpect.EOF, timeout=10)
        out = ANSI.sub("", s.child.before)
        assert "Configuration Error" in out and "max_entries" in out
    finally:
        s.close()


# -- Ctrl-C ---------------------------------------------------------------------

def test_ctrl_c_at_the_prompt_discards_the_line(session):
    session.child.send("echo not-run")
    session.child.sendcontrol("c")
    session.wait_prompt()
    assert session.output_of("echo after") == "after"


def test_ctrl_c_interrupts_a_builtin_and_the_next_command_still_runs(session):
    session.child.sendline("read VAR")
    time.sleep(0.5)
    session.child.sendcontrol("c")
    session.wait_prompt()
    assert session.output_of("echo $?") == "130"
    assert session.output_of("echo next") == "next"


def test_ctrl_c_interrupts_an_external_command(session):
    session.child.sendline("sleep 30")
    time.sleep(0.5)
    session.child.sendcontrol("c")
    session.wait_prompt()
    assert session.output_of("echo $?") == "130"


# -- job control ----------------------------------------------------------------

def test_stop_background_foreground(session):
    session.child.sendline("sleep 30")
    time.sleep(0.5)
    session.child.sendcontrol("z")
    out = session.wait_prompt()
    assert "Stopped" in out
    assert "sleep 30" in session.output_of("bg")
    assert "Running" in session.output_of("jobs")
    session.child.sendline("fg")
    time.sleep(0.5)
    session.child.sendcontrol("c")
    session.wait_prompt()
    assert "sleep" not in session.output_of("jobs")


def test_background_job_pid_and_hangup_on_exit(session):
    out = session.output_of("sleep 300 &")
    pid = int(re.search(r"\[1\] (\d+)", out).group(1))
    assert session.output_of("echo $!") == str(pid)
    session.exit()
    time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


# -- leaving ------------------------------------------------------------------

def test_exit_restores_the_terminal(session):
    fd = session.child.child_fd
    during = termios.tcgetattr(fd)[3] & termios.ECHOCTL
    assert during == 0  # the shell clears ECHOCTL while it runs
    out = session.exit()
    assert "Closing shell" in out
    assert termios.tcgetattr(fd)[3] & termios.ECHOCTL


def test_history_is_shared_and_private(home):
    exe = _zem_executable()
    first = Session(exe, home)
    first.wait_prompt()
    first.run("echo remembered")
    first.exit()
    first.close()

    history = home / ".zem_history"
    assert oct(history.stat().st_mode & 0o777) == "0o600"

    second = Session(exe, home)
    try:
        second.wait_prompt()
        assert "echo remembered" in second.output_of("history")
        second.run("echo again")
        assert second.output_of("!!").endswith("again")  # bash echoes the expansion first
    finally:
        second.close()
