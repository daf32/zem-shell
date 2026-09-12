"""The command line: `zem -c`, scripts, stdin, and argument errors."""

import io
import json

import pytest

from zem.main import main


@pytest.fixture
def cli(capfd, monkeypatch):
    """Run `main(argv)` with stdin closed; return (code, out, err)."""
    def _run(argv, stdin=""):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        capfd.readouterr()
        code = main(argv)
        captured = capfd.readouterr()
        return code, captured.out, captured.err

    return _run


def test_command_runs_and_prints(cli):
    code, out, _ = cli(["-c", "echo hi"])
    assert code == 0 and out.strip() == "hi"


def test_exit_status_is_the_last_command_s(cli):
    assert cli(["-c", "false"])[0] == 1
    assert cli(["-c", "true"])[0] == 0


def test_explicit_exit_wins(cli):
    assert cli(["-c", "exit 3"])[0] == 3


def test_pipelines_and_operators_work(cli):
    code, out, _ = cli(["-c", "echo a | tr a-z A-Z"])
    assert code == 0 and out.strip() == "A"
    code, out, _ = cli(["-c", "false || echo fallback"])
    assert out.strip() == "fallback"


def test_several_lines_in_one_command(cli):
    code, out, _ = cli(["-c", "echo one\necho two"])
    assert code == 0 and out.split() == ["one", "two"]


def test_script_file(cli, tmp_path):
    script = tmp_path / "demo.zem"
    script.write_text("# a comment\n\necho from-a-file\n")
    code, out, _ = cli([str(script)])
    assert code == 0 and out.strip() == "from-a-file"


def test_missing_script(cli, tmp_path):
    code, _, err = cli([str(tmp_path / "nope.zem")])
    assert code == 127 and "no such file" in err


def test_script_from_stdin(cli):
    code, out, _ = cli([], stdin="echo piped\n")
    assert code == 0 and out.strip() == "piped"


def test_version(cli):
    code, out, _ = cli(["--version"])
    assert code == 0 and out.startswith("zem ")


def test_help(cli):
    code, out, _ = cli(["--help"])
    assert code == 0 and "Usage:" in out and "-c COMMAND" in out


def test_unknown_option_is_an_error(cli):
    # This used to be ignored, and a session opened instead.
    code, _, err = cli(["--hepl"])
    assert code == 2 and "unknown option" in err


def test_c_without_a_command(cli):
    code, _, err = cli(["-c"])
    assert code == 2 and "needs a command" in err


def test_c_and_a_script_together(cli, tmp_path):
    script = tmp_path / "s.zem"
    script.write_text("echo x\n")
    code, _, err = cli(["-c", "echo y", str(script)])
    assert code == 2 and "mutually exclusive" in err


def test_script_arguments_are_refused_clearly(cli, tmp_path):
    script = tmp_path / "s.zem"
    script.write_text("echo x\n")
    code, _, err = cli([str(script), "arg"])
    assert code == 2 and "not supported yet" in err


def _config_with_rc(tmp_path, monkeypatch):
    rc = tmp_path / "zemrc"
    rc.write_text("alias greet='echo from-rc'\n")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "rc": {"auto_create": False, "file": str(rc)},
        "history": {"enable": False, "file": str(tmp_path / "hist")},
        "venv": {"auto": False},
    }))
    monkeypatch.setenv("ZEM_CONFIG_PATH", str(config))
    import zem.config.settings as settings

    monkeypatch.setattr(settings, "CONFIG_PATH", str(config))
    return rc


def test_rc_is_not_read_by_default(cli, tmp_path, monkeypatch):
    """A script must behave the same on a machine whose owner has never
    customised anything -- as in bash, zsh and fish."""
    _config_with_rc(tmp_path, monkeypatch)
    code, _, _ = cli(["-c", "greet"])
    assert code != 0


def test_rc_flag_reads_it(cli, tmp_path, monkeypatch):
    _config_with_rc(tmp_path, monkeypatch)
    code, out, _ = cli(["--rc", "-c", "greet"])
    assert code == 0 and out.strip() == "from-rc"
